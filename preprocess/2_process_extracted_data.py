import argparse
import csv
import glob
import io
import json
import os
import re
import shutil
import zipfile

import openpyxl
import pandas as pd

parser = argparse.ArgumentParser(description="Process extracted data")
parser.add_argument(
    "--extract-data-dir",
    type=str,
    default="./extract_output/",
    help="Extracted data directory",
)
parser.add_argument(
    "--save-dir",
    type=str,
    default="./processed_output/",
    help="Directory to save results",
)

args = parser.parse_args()


def get_xlsx_content(file_path):
    workbook = openpyxl.load_workbook(file_path, read_only=True)
    worksheet = workbook.active
    output = io.StringIO()

    csv_writer = csv.writer(output)
    for row in worksheet.iter_rows(values_only=True):
        csv_writer.writerow(row)

    output_str = output.getvalue()

    output_str = (
        output_str.replace(" _x000D_", "").replace("_x000D_", "").replace("\r\n", "\n")
    )
    return output_str


def json2df(root_path):

    def add_data(style, item_id, data):
        style_list.append(style)
        id_list.append(item_id)
        data_list.append(data)

    with open(root_path + "/structuredData.json") as f:
        data = json.load(f)

    style_list, id_list, data_list = [], [], []

    curr_page = 1
    image_count, table_count = 1, 1

    add_data("Page_Start", 1, None)

    for item in data["elements"]:
        # clean the item
        if "Text" in item:
            item["Text"] = item["Text"].replace("�", "")
            item["Text"] = item["Text"].replace("", "")

        if (
            "Page" in item and (item["Page"] + 1) > curr_page
        ):  # Page attribute is 0-indexed
            curr_page = item["Page"] + 1
            add_data("Page_Start", str(curr_page), None)

        if "/Table" in item["Path"]:
            if "filePaths" in item:
                table_data = {}
                for file_path in item["filePaths"]:
                    if file_path[-4:] == "xlsx":
                        table_content = get_xlsx_content(root_path + file_path)
                        table_data["content"] = table_content
                    else:  # image
                        table_data["image_path"] = file_path

                add_data("Table", table_count, table_data)
                table_count += 1

        elif "/Figure" in item["Path"]:
            if "filePaths" in item:
                for file_path in item["filePaths"]:
                    image_data = {"path": file_path}
                    if "alternate_text" in item:
                        image_data["alt_text"] = item["alternate_text"]
                    else:
                        image_data["alt_text"] = None
                    add_data("Image", image_count, image_data)
                    image_count += 1

            elif "Text" in item:
                add_data("Caption", None, item["Text"])

        elif re.search(r"/H(\d+)", item["Path"]) and "Text" in item:

            heading_num = re.findall(r"/H(\d+)", rf"{item["Path"]}")[0]
            heading_name = f"Heading {heading_num}"
            if style_list[-1] == heading_name:
                data_list[-1] += " " + item["Text"]
            else:
                add_data(heading_name, None, item["Text"])

        elif "/P" in item["Path"] and "Text" in item:
            add_data("Normal", None, item["Text"])

        elif "/Footnote" in item["Path"] and "Text" in item:
            add_data("Footnote", None, item["Text"])

        elif "/LBody" in item["Path"] and "Text" in item:
            add_data("List Paragraph", None, item["Text"])

        elif "/Title" in item["Path"]:
            add_data("Title", None, item["Text"])

    df = pd.DataFrame(
        {"para_text": data_list, "table_id": id_list, "style": style_list}
    )
    return df


def main(args):

    os.makedirs(args.save_dir, exist_ok=True)
    for zip_path in glob.glob(args.extract_data_dir + "/*.zip"):
        sid = zip_path.split("/")[-1][:-4]
        print(sid)
        root_path = f"{args.extract_data_dir}/{sid}/"
        # Unzip a file
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(root_path)

        df = json2df(root_path + "/")

        save_path = f"{args.save_dir}/{sid}/"
        os.makedirs(save_path, exist_ok=True)
        df.to_pickle(save_path + "/data.pkl")

        # if PDF contains images or tables, copy the images and tables
        if os.path.exists(root_path + "/figures"):
            shutil.copytree(
                root_path + "/figures", save_path + "/figures", dirs_exist_ok=True
            )
        if os.path.exists(root_path + "/tables"):
            shutil.copytree(
                root_path + "/tables", save_path + "/tables", dirs_exist_ok=True
            )


if __name__ == "__main__":
    main(args)
