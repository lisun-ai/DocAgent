import json
import re
import time
import traceback
import xml.dom.minidom
import xml.etree.ElementTree as ET

from openai import OpenAI

from prompts import (actor_prompt_template, available_tools,
                     reflection_prompt_template, reviewer_prompt,
                     system_prompt)


def clean_xml_string(xml_str):
    cleaned = "".join(char for char in xml_str if char.isprintable() or char.isspace())
    return cleaned


class DocAgent:
    def __init__(
        self,
        doc_reader,
        model_id="gpt-4o",
        temperature=0.0,
        max_tokens=8192,
        api_key=None,
        tool_call_wait_time=10,
    ):
        self.doc_reader = doc_reader
        self.model_id = model_id
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = OpenAI(api_key=api_key)
        self.tool_call_wait_time = tool_call_wait_time

    def get_outline(self):

        outline = self.doc_reader.get_outline_root()

        xml_string = ET.tostring(outline, encoding="unicode", method="xml")
        xml_string = clean_xml_string(xml_string)
        dom = xml.dom.minidom.parseString(xml_string)
        xml_string = (
            dom.toprettyxml(indent="  ", newl="\n")
            .split("\n", 1)[1]
            .replace("&quot;", "")
        )
        return xml_string

    def run_actor(self, question, memory, tools=available_tools):
        xml_string = self.get_outline()
        initial_prompt = actor_prompt_template.format(
            document_outline=xml_string, question=question, memory=memory
        )

        initial_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": initial_prompt},
        ]
        final_response, messages = self.run_agent(initial_messages, tools=tools)
        return final_response, messages

    def run_reviewer(
        self,
        initial_messages,
        initial_prompt=reviewer_prompt,
        tools=available_tools,
        extract_regex=r"<final_result>(.*)</final_result>",
    ):

        messages = []

        for item in initial_messages:
            # remove id, token_usage
            if "model" in item:  # from assistant
                messages.append(item["choices"][0]["message"])

            else:  # others
                messages.append(item)

        messages.append({"role": "user", "content": initial_prompt})

        final_response, messages = self.run_agent(
            messages, tools=tools, extract_regex=extract_regex
        )
        return final_response, messages

    def run_reflection(
        self,
        initial_messages,
        memory,
        tools=available_tools,
        extract_regex=r"<updated_guideline>(.*)</updated_guideline>",
    ):

        initial_prompt = reflection_prompt_template.format(memory=memory)

        messages = []

        for item in initial_messages:
            # remove id, token_usage
            if "model" in item:  # from assistant
                messages.append(item["choices"][0]["message"])

            else:  # others
                messages.append(item)

        messages.append({"role": "user", "content": initial_prompt})

        memory_new, messages_memory = self.run_agent(
            messages, tools=tools, extract_regex=extract_regex
        )
        return memory_new, messages_memory

    def run_agent(
        self,
        initial_messages,
        tools,
        extract_regex=r"<final_result>(.*)</final_result>",
        max_num_tool=10,
        max_round=10,
    ):

        messages = initial_messages
        messages_full = messages.copy()

        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                tools=tools,
                tool_choice="auto",
            )

            # limit the number of tools called in one turn
            if (
                response.choices[0].message.tool_calls
                and len(response.choices[0].message.tool_calls) > max_num_tool
            ):
                response.choices[0].message.tool_calls = response.choices[
                    0
                ].message.tool_calls[:max_num_tool]

            messages_full.append(response.to_dict())
            messages.append(response.choices[0].message)

            # tools are callled
            num_round = 0
            while response.choices[0].message.tool_calls:
                # Wait to reduce rate limit errors
                time.sleep(self.tool_call_wait_time)

                # LLM can call multiple functions in one turn
                tool_response_tool, tool_response_user = [], []
                for tool_call in response.choices[0].message.tool_calls:
                    tool_response = self.get_reply_for_tool(
                        {
                            "type": "tool_use",
                            "id": tool_call.id,
                            "name": tool_call.function.name,
                            "input": json.loads(tool_call.function.arguments),
                        }
                    )
                    if len(tool_response) > 1:  # tool reply with image
                        tool_response_tool.append(tool_response[0])
                        tool_response_user.extend(tool_response[1:])
                    else:
                        tool_response_tool.extend(tool_response)
                # tool calls must follow by tool response
                messages.extend(tool_response_tool + tool_response_user)
                messages_full.extend(tool_response_tool + tool_response_user)

                if num_round >= max_round:
                    tool_choice = "none"
                    print("Exceed max_round, stop calling tools")
                else:
                    tool_choice = "auto"
                response = self.client.chat.completions.create(
                    model=self.model_id,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    tools=tools,
                    tool_choice=tool_choice,
                )

                # limit the number of tools called in one turn
                if (
                    response.choices[0].message.tool_calls
                    and len(response.choices[0].message.tool_calls) > max_num_tool
                ):
                    response.choices[0].message.tool_calls = response.choices[
                        0
                    ].message.tool_calls[:max_num_tool]
                messages_full.append(response.to_dict())
                messages.append(response.choices[0].message)
                num_round += 1

            match_result = re.search(
                extract_regex, response.choices[0].message.content, re.DOTALL
            )
            if match_result is not None:
                final_response = match_result.group(1)
            else:
                final_response = response.choices[0].message.content

            return final_response.strip(), messages_full

        except Exception as e:
            print(traceback.format_exc())
            return str(e), messages_full

    def package_content(self, item, tool_use_id=None, image_content=None):
        if image_content is not None:  # tool reply with text and image
            content = [{"type": "text", "text": item}]
            for item in image_content:
                media_type, base64_image = item
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{base64_image}"
                        },
                    }
                )
            # As of Nov 2024, GPT-4o doesn't support tool response with image, therefore we package image in user message
            return [
                {
                    "role": "tool",
                    "content": "The result from tool is returned in the following user message:",
                    "tool_call_id": tool_use_id,
                },
                {"role": "user", "content": content, "tool_call_id": tool_use_id},
            ]
        else:  # tool only reply with text
            content = item
            return [{"role": "tool", "content": content, "tool_call_id": tool_use_id}]

    def get_reply_for_tool(self, item, max_search_results=24, max_page_images=20):

        if item["type"] == "tool_use":
            tool_use_id = item["id"]
            if item["name"] == "search":
                keyword = item["input"]["keyword"]
                search_root = self.doc_reader.search(keyword)
                if len(search_root) == 0:
                    result_text = f"We didn't find any section or paragraph that contains the keyword {keyword}"

                else:
                    if len(search_root) > max_search_results:
                        for subelement in search_root[max_search_results:]:
                            search_root.remove(subelement)

                        result_text = f"We found {str(len(search_root))} results that contain the keyword {keyword}. To shorten response, the first {max_search_results} results are listed below:\n"
                    else:
                        result_text = f"We found {str(len(search_root))} results that contain the keyword {keyword}, listed below:\n"
                    xml_string = ET.tostring(
                        search_root, encoding="unicode", method="xml"
                    )
                    xml_string = clean_xml_string(xml_string)
                    dom = xml.dom.minidom.parseString(xml_string)
                    xml_string = dom.toprettyxml(indent="  ", newl="\n").split("\n", 1)[
                        1
                    ]
                    result_text = result_text + xml_string

                return self.package_content(result_text, tool_use_id=tool_use_id)

            elif item["name"] == "get_section_content":
                section_id = str(item["input"]["section_id"])
                if section_id not in self.doc_reader.section_dict.keys():
                    result_text = f"The section_id {section_id} is not presented in the document, here is the full list of available section_id: {list(self.doc_reader.section_dict.keys())}. Please try again."

                else:
                    section_root = self.doc_reader.get_section_content(section_id)

                    xml_string = ET.tostring(
                        section_root, encoding="unicode", method="xml"
                    )
                    xml_string = clean_xml_string(xml_string)
                    dom = xml.dom.minidom.parseString(xml_string)
                    xml_string = dom.toprettyxml(indent="  ", newl="\n").split("\n", 1)[
                        1
                    ]
                    if len(xml_string) > 30000:
                        xml_string = (
                            xml_string[:30000]
                            + "\n...The content is too long. Try to get the content in sub sections."
                        )
                        result_text = (
                            f"Here is the text content of Section {section_id}:\n"
                            + xml_string
                        )
                    else:
                        result_text = (
                            f"Here is the full text content of Section {section_id}:\n"
                            + xml_string
                        )

                return self.package_content(result_text, tool_use_id=tool_use_id)

            elif item["name"] == "get_page_images":
                start_page_num = int(item["input"]["start_page_num"])

                end_page_num = int(item["input"]["end_page_num"]) + 1
                result_text = ""
                if start_page_num < 1:
                    result_text = (
                        result_text + "The start_page_num cannot be smaller than 1. "
                    )
                elif start_page_num > self.doc_reader.num_page:
                    result_text = (
                        result_text
                        + f"The start_page_num cannot be greater than max_page_num {str(self.doc_reader.num_page)}. "
                    )
                if end_page_num < 1:
                    result_text = (
                        result_text + "The end_page_num cannot be smaller than 1. "
                    )
                elif end_page_num > self.doc_reader.num_page:
                    result_text = (
                        result_text
                        + f"The end_page_num cannot be greater than max_page_num {str(self.doc_reader.num_page)}. "
                    )

                if len(result_text) > 0:
                    return self.package_content(
                        result_text + "Please try again",
                        tool_use_id=tool_use_id,
                    )

                else:
                    image_content = []
                    # end_page_num is included
                    for page_num in range(
                        start_page_num,
                        min(end_page_num + 1, start_page_num + max_page_images + 1),
                    ):
                        media_type, base64_image, error = (
                            self.doc_reader.get_page_image(page_num)
                        )
                        if error is not None:
                            raise Exception(
                                f"Error in extracting page_image {str(page_num)}: {str(error)}"
                            )
                        image_content.append([media_type, base64_image])
                    if end_page_num > start_page_num + max_page_images:
                        result_text = f"Here are the page images for page {str(start_page_num)} to page {str(start_page_num+max_page_images)}, as the number of page images exceeds the maximum limit of {str(max_page_images)}"
                    else:
                        result_text = f"Here are the page images for page {str(start_page_num)} to page {str(end_page_num)}"
                    return self.package_content(
                        result_text,
                        tool_use_id=tool_use_id,
                        image_content=image_content,
                    )

            elif item["name"] == "get_image":
                image_id = str(item["input"]["image_id"])
                if image_id not in self.doc_reader.image_path_dict:
                    result_text = f"The image_id {image_id} is not presented in the document, here is the full list of available image_id: {list(self.doc_reader.image_path_dict.keys())}. Please try again"

                    return self.package_content(result_text, tool_use_id=tool_use_id)

                else:
                    media_type, base64_image, error = self.doc_reader.get_image(
                        image_id
                    )
                    if error is not None:
                        raise Exception(
                            f"Error in extracting image {str(image_id)}: {str(error)}"
                        )
                    result_text = f"Here is the image content for image_id {image_id}"

                    return self.package_content(
                        result_text,
                        tool_use_id=tool_use_id,
                        image_content=[[media_type, base64_image]],
                    )

            elif item["name"] == "get_table_image":
                table_id = str(item["input"]["table_id"])
                if table_id not in self.doc_reader.table_image_path_dict:
                    result_text = f"The table {table_id} doesn't have a corresponding image, here is the full list of table_id that companies an image: {list(self.doc_reader.table_image_path_dict.keys())}. Please try again."

                    return self.package_content(result_text, tool_use_id=tool_use_id)

                else:
                    media_type, base64_image, error = self.doc_reader.get_table_image(
                        table_id
                    )
                    if error is not None:
                        raise Exception(
                            f"Error in extracting image for table {str(table_id)}: {str(error)}"
                        )
                    result_text = f"Here is the image content for table_id {table_id}"

                    return self.package_content(
                        result_text,
                        tool_use_id=tool_use_id,
                        image_content=[[media_type, base64_image]],
                    )

            else:
                result_text = f"Tool {item["name"]} is not valid, here is the list of available tools: [search, get_section_data, get_page_images, get_image]. Please try again."
                return self.package_content(result_text, tool_use_id=tool_use_id)
