# Reference: https://www.anthropic.com/research/swe-bench-sonnet
# https://github.com/anthropics/anthropic-quickstarts/blob/bbff506357f0ef2e944cba582bcfaf6fad7f7261/customer-support-agent/app/api/chat/route.ts#L119
system_prompt = """
You are an expert research assistant tasked with answering questions based on document content. 
"""


actor_prompt_template = """I've uploaded a document, and below is the outline in XML format:
{document_outline}

Can you answer the following question based on the content of the document?
<question>
{question}
</question>

Follow these steps to answer the question:
1. As a first step, it might be a good idea to explore the document with the provided tools to familiarize yourself with its structure.
2. Locate the source in the document that can be used to answer the question. Then retrieve the full content of the source in the document with tools to examine it in detail.
3. Find the quote from the document that are most relevant to answering the question, and put it within the <quote></quote> tags. If there are no relevant quotes, write "No relevant quotes" instead.
4. When you gather enough information, return the final concise answer within the <final_result></final_result> tags, leave the explanation outside of the <final_result> tags.

Important guidelines:
- Be aware that the document content is obtained using OCR, so there may be scanning errors or typos.
- Before each step, wrap your thought process in <analysis></analysis> tags. This will help ensure a thorough and accurate analysis of the document and question.
{memory}"""


reviewer_prompt = """
Now, please validate the answer using the tools to retrieve the source of information that can be used to answer the question. Only use necessary tools. Return the final concise answer within the <final_result></final_result> tags, leave the explanation outside of the <final_result> tags. 
"""

reflection_prompt_template = """Please update the reflection listed within the <guideline></guideline> tags below that can help you perform better next time. Provide the updated guidance within the <updated_guideline></updated_guideline> tags. Be concise and clear. Ensure the revised guideline deviates from the original by at most one sentence.

<guideline>{memory}</guideline>"""


search_tool_description = {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Find and extract all paragraphs and sections where the exact search term appears",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "The query keyword for searching"
                    }
                },
                "required": ["keyword"]
            }
        }
    }
get_section_content_tool_description = {
        "type": "function",
        "function": {
            "name": "get_section_content",
            "description": "Get the full-text content of a section in XML format",
            "parameters": {
                "type": "object",
                "properties": {
                    "section_id": {
                        "type": "string",
                        "description": "The ID of the section from which to fetch the complete content"
                    }
                },
                "required": ["section_id"]
            }
        }
    }
get_page_images_tool_description = {
        "type": "function",
        "function": {
            "name": "get_page_images",
            "description": "Extract full-page images from a specified range of pages. Both the starting page and ending page are included. Page numbers are 1-indexed",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_page_num": {
                        "type": "integer",
                        "description": "The first page number for page image extraction"
                    },
                    "end_page_num": {
                        "type": "integer",
                        "description": "The last page number for page image extraction"
                    }
                },
                "required": ["start_page_num", "end_page_num"]
            }
        }
    }
get_image_tool_description = {
        "type": "function",
        "function": {
            "name": "get_image",
            "description": "Get the visual content of an image",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_id": {
                        "type": "string",
                        "description": "The ID of the image from which to fetch the visual content"
                    }
                },
                "required": ["image_id"]
            }
        }
    }
get_table_image_tool_description = {
        "type": "function",
        "function": {
            "name": "get_table_image",
            "description": "Get the screenshot of a table. Use this tool to double-check the content of the table",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_id": {
                        "type": "string",
                        "description": "The ID of the table from which to fetch the screenshot"
                    }
                },
                "required": ["table_id"]
            }
        }
    }

available_tools = [search_tool_description, get_section_content_tool_description, get_page_images_tool_description, get_image_tool_description, get_table_image_tool_description]