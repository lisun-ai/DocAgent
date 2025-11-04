import base64
import copy
import glob
import os
import xml.etree.ElementTree as ET
from typing import Optional, Tuple

import pandas as pd
from PIL import Image


def process_image(image_path: str) -> Tuple[str, str, Optional[str]]:

    try:
        # Check if file exists
        if not os.path.exists(image_path):
            return "", "", "File not found"

        # Get file extension and determine media type
        _, extension = os.path.splitext(image_path)
        extension = extension.lower()

        # Map common image extensions to MIME types
        media_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }

        media_type = media_types.get(extension)
        if not media_type:
            return "", "", f"Unsupported image format: {extension}"

        image_size = os.path.getsize(image_path) / 1024.0 / 1024.0  # size in MB
        if image_size > 1 and extension != ".jpg":
            # save the image as compressed jpg
            compress_image_path = image_path[:-4] + "_compressed.jpg"
            if not os.path.exists(compress_image_path):
                img = Image.open(image_path)
                img.save(compress_image_path)

            image_path = compress_image_path
            media_type = "image/jpeg"

        # Read and encode the image
        with open(image_path, "rb") as image_file:
            binary_data = image_file.read()
            base64_image = base64.b64encode(binary_data).decode("utf-8")

        # compress the image

        return media_type, base64_image, None

    except Exception as e:
        return "", "", f"Error processing image: {str(e)}"


class DocReader:
    """
    A class to read and process document data, converting it into an XML structure.
    Attributes:
    -----------
    data_path : str
        The path to the directory containing the document data.
    data : pandas.DataFrame
        The data read from the pickle file.
    root : xml.etree.ElementTree.Element
        The root element of the XML structure.
    image_count : int
        Counter for the number of images.
    table_count : int
        Counter for the number of tables.
    para_count : int
        Counter for the number of paragraphs.
    section_dict : dict
        Dictionary mapping section IDs to their corresponding XML elements.
    image_path_dict : dict
        Dictionary mapping image IDs to their file paths.
    table_image_path_dict : dict
        Dictionary mapping table IDs to their image file paths.
    num_page : int
        The number of pages in the document.
    Methods:
    --------
    __init__(data_path):
        Initializes the DocReader with the given data path and processes the document data.
    get_outline_root():
        Returns a deep copy of the root element with the tag changed to "Outline" and paragraphs modified.
    get_section_content(section_id):
        Returns the XML element corresponding to the given section ID.
    get_image(image_id):
        Returns the processed image for the given image ID.
    get_page_image(page_num):
        Returns the processed image for the given page number.
    get_table_image(table_id):
        Returns the processed image for the given table ID.
    search(key_word):
        Searches for the given keyword in the document and returns an XML element with the search results.
    """

    def __init__(self, data_path, max_section_depth=10):
        self.data_path = data_path
        self.data = pd.read_pickle(self.data_path + "/data.pkl")

        prev_heading_num = 0
        self.root = ET.Element("Document")
        prev_node = self.root
        stack = [(prev_node, prev_heading_num)]
        self.image_count, self.table_count, self.para_count = 0, 0, 0

        self.section_dict = dict()
        self.image_path_dict = dict()
        self.table_image_path_dict = dict()
        prev_section_id = ""  # root id
        self.num_page = len(glob.glob(self.data_path + "/page_images/*.png"))
        self.max_section_depth = max_section_depth

        index = 0
        curr_page_num = 1
        if not self.data.iloc[0]["style"].startswith(
            "Heading"
        ):  # if first element is not heading
            curr_section_id = "1"
            curr_node = ET.SubElement(
                prev_node,
                "Section",
                section_id=curr_section_id,
                start_page_num=str(curr_page_num),
            )

            self.section_dict[curr_section_id] = curr_node
            stack.append([curr_node, 1])

            prev_section_id = curr_section_id
            prev_node = curr_node

        while index < len(self.data):
            row = self.data.iloc[index]

            if row["style"].startswith("Heading"):
                curr_heading_num = int(row["style"].split()[1])

                while (
                    curr_heading_num < stack[-1][1]
                ):  # curr element is of higher rank than prev element
                    stack[-1][0].set("end_page_num", str(curr_page_num))
                    stack.pop()
                    prev_section_id_list = prev_section_id.split(".")
                    prev_section_id = ".".join(prev_section_id_list[:-1])

                if (
                    curr_heading_num == stack[-1][1]
                ):  # curr element is of equal rank of prev element
                    stack[-1][0].set("end_page_num", str(curr_page_num))
                    curr_section_id_list = prev_section_id.split(".")
                    curr_section_id_list[-1] = str(int(curr_section_id_list[-1]) + 1)
                    curr_section_id = ".".join(curr_section_id_list)
                    prev_node = stack[-2][0]

                    curr_node = ET.SubElement(
                        prev_node,
                        "Section",
                        section_id=curr_section_id,
                        start_page_num=str(curr_page_num),
                    )
                    self.section_dict[curr_section_id] = curr_node
                    heading = ET.SubElement(curr_node, "Heading")
                    heading.text = row["para_text"].strip()

                    stack[-1][0] = curr_node

                else:  # curr element is of lower rank than prev element
                    if len(stack) <= self.max_section_depth:
                        prev_node = stack[-1][0]
                        curr_section_id = prev_section_id + ".1"
                        curr_node = ET.SubElement(
                            prev_node,
                            "Section",
                            section_id=curr_section_id,
                            start_page_num=str(curr_page_num),
                        )
                        self.section_dict[curr_section_id] = curr_node
                        heading = ET.SubElement(curr_node, "Heading")
                        heading.text = row["para_text"].strip()

                        stack.append([curr_node, curr_heading_num])
                    else:
                        # view as paragraph to avoid too deep section
                        content = row["para_text"]
                        while index + 1 < len(self.data) and self.data.iloc[index + 1][
                            "style"
                        ] in ["Normal", "Body Text", "List Paragraph", "Footnote"]:
                            index += 1
                            content = content + " " + self.data.iloc[index]["para_text"]

                        para = ET.SubElement(
                            prev_node, "Paragraph", page_num=str(curr_page_num)
                        )
                        para.text = content

                        self.para_count += 1
                        index += 1
                        continue  # do not update prev_node and prev_section_id

                prev_section_id = curr_section_id
                prev_node = curr_node

            elif row["style"] in ["Normal", "Body Text", "List Paragraph", "Footnote"]:
                curr_style = row["style"]
                content = row["para_text"]
                while (
                    index + 1 < len(self.data)
                    and self.data.iloc[index + 1]["style"] == curr_style
                ):
                    index += 1
                    content = content + " " + self.data.iloc[index]["para_text"]

                para = ET.SubElement(
                    prev_node, "Paragraph", page_num=str(curr_page_num)
                )
                para.text = content

                self.para_count += 1

            elif row["style"] == "Image":
                item = row["para_text"]
                image = ET.SubElement(
                    prev_node,
                    "Image",
                    image_id=str(self.image_count),
                    page_num=str(curr_page_num),
                )
                self.image_path_dict[str(self.image_count)] = os.path.basename(
                    item["path"]
                )

                if item["alt_text"] is not None:

                    alt_text = ET.SubElement(image, "Alt_Text")
                    alt_text.text = str(item["alt_text"])
                self.image_count += 1

            elif row["style"] == "Caption":
                prev_row = self.data.iloc[index - 1]
                if prev_row["style"] == "Image":
                    caption = ET.SubElement(image, "Caption")
                else:
                    caption = ET.SubElement(prev_node, "Caption")

                caption.text = str(row["para_text"])

            elif row["style"] == "Table":

                if len(row["para_text"]) == 0 or "content" not in row["para_text"]:
                    index += 1
                    continue
                table = ET.SubElement(
                    prev_node,
                    "CSV_Table",
                    table_id=str(self.table_count),
                    page_num=str(curr_page_num),
                )

                table.text = row["para_text"]["content"]
                if "image_path" in row["para_text"]:
                    self.table_image_path_dict[str(self.table_count)] = row[
                        "para_text"
                    ]["image_path"]
                self.table_count += 1

            elif row["style"] == "Page_Start":
                curr_page_num = row["table_id"]

            elif row["style"] == "Title":
                content = row["para_text"]

                para = ET.SubElement(prev_node, "Title", page_num=str(curr_page_num))
                para.text = content

            else:
                print("Uncovered style:", row["style"])
                raise Exception
            index += 1
        for i in range(len(stack)):
            if stack[i][0].tag == "Section":
                stack[i][0].set("end_page_num", str(curr_page_num))

    def get_outline_root(
        self, skip_para_after_page=100, disable_caption_after_page=False
    ):
        def iterator(parent):
            for child in reversed(parent):
                if len(child) >= 1 and child.tag == "Section":
                    iterator(child)
                if child.tag == "Paragraph":
                    if (
                        int(float(child.get("page_num"))) > skip_para_after_page
                    ):  # avoid too long outline
                        parent.remove(child)
                    else:
                        child.set("first_sentence", child.text.split(". ", 1)[0])
                        child.text = None
                if child.tag == "CSV_Table":
                    if (
                        int(float(child.get("page_num"))) > skip_para_after_page
                    ):  # avoid too long outline
                        child.text = None
                if child.tag == "Image" and disable_caption_after_page:
                    if int(float(child.get("page_num"))) > disable_caption_after_page:
                        for sub_child in child:
                            if (
                                sub_child.tag == "Caption"
                                and sub_child.text is not None
                            ):
                                # Truncate caption text to 20 characters to save context length
                                sub_child.text = sub_child.text[:20] 

        root = copy.deepcopy(self.root)
        root.tag = "Outline"
        iterator(root)

        return root

    def get_section_content(self, section_id):
        return self.section_dict[section_id]

    def get_image(self, image_id):

        image_path = self.data_path + "/figures/" + self.image_path_dict[image_id]
        return process_image(image_path)

    def get_page_image(self, page_num):

        index_string = "%04d" % (int(page_num) - 1)
        image_path = self.data_path + "/page_images/page_" + index_string + ".png"
        return process_image(image_path)

    def get_table_image(self, table_id):

        image_path = self.data_path + "/" + self.table_image_path_dict[table_id]
        return process_image(image_path)

    def search(self, key_word):
        key_word = key_word.lower()

        result_root = ET.Element("Search_Result")
        curr_section_id = ""

        for curr in self.root.iter():
            if curr.tag == "Section":
                curr_section_id = curr.get("section_id")

                if (
                    len(curr) > 0
                    and curr[0].text is not None
                    and key_word in curr[0].text.lower()
                ):  # heading
                    item = ET.SubElement(
                        result_root,
                        "Item",
                        type="Section",
                        section_id=curr_section_id,
                        page_num=curr.get("start_page_num"),
                    )
                    item.text = curr[0].text  # get heading

            elif curr.tag in ["Paragraph", "CSV_Table"]:
                if key_word in curr.text.lower():
                    item = ET.SubElement(
                        result_root,
                        "Item",
                        type=curr.tag,
                        section_id=curr_section_id,
                        page_num=curr.get("page_num"),
                    )
                    item.text = curr.text

            elif curr.tag == "Image":
                keyword_found = False
                for child in curr:
                    if key_word in child.text.lower():
                        keyword_found = True
                        break
                if keyword_found:
                    item = ET.SubElement(
                        result_root,
                        "Image",
                        type=curr.tag,
                        image_id=curr.get("image_id"),
                        section_id=curr_section_id,
                        page_num=curr.get("page_num"),
                    )
                    for child in curr:
                        sub_item = ET.SubElement(item, child.tag)
                        sub_item.text = child.text

        return result_root
