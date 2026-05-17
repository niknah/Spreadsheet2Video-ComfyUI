from comfy_execution.graph_utils import GraphBuilder, is_link
from comfy_execution.graph import ExecutionBlocker
from comfy_api.latest import io
from nodes import NODE_CLASS_MAPPINGS
from server import PromptServer
import csv
import hashlib
from io import StringIO
import numpy as np
from PIL import Image
from pathlib import Path
import folder_paths
import random
import logging
import torch
import torchaudio
import re
import time
import datetime
import pandas as pd



class S2VComfy():
    @classmethod
    def get_prompt_id(cls):
        queue = PromptServer.instance.prompt_queue.get_current_queue_volatile()
        return list(list(queue)[0])[0][1]

    @classmethod
    def get_prompt_dir(cls):
        temp_dir = Path(folder_paths.get_temp_directory()) / f"Spreadsheet2Video_{cls.get_prompt_id()}"
        temp_dir.mkdir(exist_ok=True)
        return temp_dir


    @classmethod
    def get_all_files(cls, prefix):
        prompt_dir = cls.get_prompt_dir()
        # this could be quicker if we kept track
        files = [
            entry for entry in prompt_dir.iterdir()
                if entry.name.startswith(prefix) 
        ]
        files.sort()
        return files

    @classmethod
    def get_next_file(cls, prefix):
        prompt_dir = cls.get_prompt_dir()
        max_num = 0
        # this could be quicker if we kept track
        for entry in prompt_dir.iterdir():
            m = re.search(r"(\d+)$", entry.stem)
            if m is not None:
                num = int(m.group(1))
                if num > max_num:
                    max_num = num
        return cls.get_prompt_dir() / ("%s%06d" % (prefix, max_num+1) )


last_processed_time = None
# Executed after each row
class Spreadsheet2VideoProcessImage(io.ComfyNode):

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="Spreadsheet2VideoProcessImage",
            display_name="Internal S2V Process Image",
            description="internal node, ignore",
            category="S2V Internal",
            inputs=[
                io.Int.Input("previous"),
                io.Image.Input("images", optional=True),
                io.Audio.Input("audio", optional=True),
            ],
            outputs=[
                io.Int.Output(),
                io.Image.Output(),
                io.Audio.Output(),
            ],
            hidden=[],
        )

    @classmethod
    def execute(cls, previous, images=None, audio=None) -> io.NodeOutput:
        global last_processed_time
        if images is not None:
            for (batch_number, image) in enumerate(images):
                next_file = S2VComfy.get_next_file("v_")
                next_file = next_file.with_suffix(".png")

                i = 255. * image.cpu().numpy()
                img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))

                logging.info(f"S2V: save img: {str(next_file)}")
            
                img.save(str(next_file), compress_level=9)

            if (images.shape[0] == 0):
                raise Exception(f"S2VProcessImage.  No image shape: {str(images.shape)}")

        if audio is not None:
            next_file = S2VComfy.get_next_file("a_")
            next_file = next_file.with_suffix(".flac")

            logging.info(f"S2V: save audio: {str(next_file)}")

            torchaudio.save(next_file, audio["waveform"][0], audio["sample_rate"], format="flac")

        output_image = None if images is None else images[-1:]

        current_time = time.time()
        if last_processed_time is not None:
            time_len = current_time - last_processed_time 
            logging.info(f"S2V: time taken for row: {datetime.timedelta(time_len/86400)}")
        last_processed_time = current_time

        return io.NodeOutput(
            # images[images.shape[0]-1,]
#            images
            previous,
            output_image,
            audio
        )

    @classmethod
    def fingerprint_inputs(s, previous=1, images=None, audio=None):
        # always run because the other nodes are not a part of this execution pth
        return str(random.random())


# Not executed
class Spreadsheet2VideoOutputImage(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="Spreadsheet2VideoOutputImage",
            display_name="Spreadsheet2Video Output Image",
            category="Spreadsheet2Video",
            search_aliases=["spreadsheet", "loop", "output"],
            inputs=[
                io.Image.Input("images", lazy=True, tooltip="Link the image or video output here."),
                io.Audio.Input("audio", lazy=True, optional=True, tooltip="Link the audio output here."),
            ],
            outputs=[
            ],
            hidden=[],
        )

    @classmethod
    def execute(cls, name) -> io.NodeOutput:
        # raise Error(f"This node should not be executed")
        return io.NodeOutput(
            ExecutionBlocker(None)
        )

    def check_lazy_status(cls, images=None):
        return []

# Not executed
class Spreadsheet2VideoInputImage(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="Spreadsheet2VideoInputImage",
            display_name="Spreadsheet2Video Input Image",
            category="Spreadsheet2Video",
            search_aliases=["spreadsheet", "loop", "output"],
            inputs=[
                io.String.Input("COLUMN1", lazy=True, tooltip="Name of this part of the workflow.  Use the same name in the spreadsheet's first column."),
            ],
            outputs=[
                io.Image.Output(),
            ],
            hidden=[],
        )

    @classmethod
    def execute(cls, COLUMN1=None) -> io.NodeOutput:
        return io.NodeOutput(
            ExecutionBlocker(None)
        )

    @classmethod
    def check_lazy_status(cls, COLUMN1=None):
        return []


class GroupInfo():
    def __init__(self, first_input_node_id, group_name):
        self.orig_node_ids = {}
        self.group_name = group_name
        self.first_input_node_id = first_input_node_id
        self.output_image_link = None


    def change_out_node(self, graph):
        output_image_node_id = None
        found_node = None
        for node_id in graph.nodes.keys():
            node = graph.nodes.get(node_id)
            if node.class_type == "Spreadsheet2VideoOutputImage":
                node.class_type = "Spreadsheet2VideoProcessImage"
                output_image_node_id = node_id
                self.output_image_link = node.out(1) # [node_id, 1]
                found_node = node

        if output_image_node_id is None:
            logging.error("S2V: Could not find output image node")
        return found_node

    @classmethod
    def map_children(cls, prompt):
        input_node_ids = []
        child_node_ids = {}
        for node_id, node in prompt.items():
            if "inputs" not in node:
                continue

            for k, v in node["inputs"].items():
                if not is_link(v):
                    continue

                parent_node_id = v[0]
                if parent_node_id not in child_node_ids:
                    child_node_ids[parent_node_id] = {"in":[], "out":[]}
                child_node_ids[parent_node_id]["out"].append(node_id)

                if node_id not in child_node_ids:
                    child_node_ids[node_id] = {"in":[], "out":[]}
                child_node_ids[node_id]["in"].append(parent_node_id)

            if node["class_type"] == "Spreadsheet2VideoInputImage":
                input_node_ids.append(node_id)

        return (child_node_ids,input_node_ids)

    @classmethod
    def add_map_output_by_group_name(cls, group_name_by_output_id, child_node_ids, children, group_name):
        for child_id in children["out"]:
            if child_id in group_name_by_output_id:
                existing_group_name = group_name_by_output_id[child_id]
                if existing_group_name != group_name:
                    raise ValueError(f"S2V: Node is in both column1 groups, node id:{child_id}, names:{existing_group_name}, {group_name}")

            group_name_by_output_id[child_id] = group_name
            if child_id not in child_node_ids:
                logging.error(f"S2V: Cannot find output node id: {child_id}")
                continue
            cls.add_map_output_by_group_name(
                group_name_by_output_id,
                child_node_ids,
                child_node_ids[child_id],
                group_name
            )

    @classmethod
    def map_output_by_group_name(cls, group_name_by_output_id, prompt):
        (child_node_ids, input_node_ids) = cls.map_children(prompt)

        for input_node_id in input_node_ids:
            inputImageNode = prompt[input_node_id]
            group_name = cls.get_group_name_from_node(inputImageNode)

            group_name_by_output_id[input_node_id] = group_name
            cls.add_map_output_by_group_name(
                group_name_by_output_id,
                child_node_ids,
                child_node_ids[input_node_id],
                group_name
            )

        return group_name_by_output_id

    @classmethod
    def get_group_name_from_node(cls, inputImageNode):
        if inputImageNode is None or "inputs" not in inputImageNode:
            return None

        group_name = inputImageNode["inputs"]["COLUMN1"].strip()
        if group_name == "":
            return None

        return group_name

    @classmethod
    def map_outputs(cls, prompt):
        (child_node_ids, input_node_ids) = cls.map_children(prompt)

        group_name_by_output_id = {}
        cls.map_output_by_group_name(group_name_by_output_id, prompt)

        by_group_name = {}
        for input_node_id in input_node_ids:
            inputImageNode = prompt[input_node_id]

            group_name = cls.get_group_name_from_node(inputImageNode)
            if group_name is None:
                continue

            if group_name in by_group_name:
                raise ValueError(f"S2V: Duplicate group names: {group_name}")

            group_info = GroupInfo(input_node_id, group_name)
            by_group_name[group_name] = group_info

            group_info.add_orig_node_ids(
                prompt,
                child_node_ids[input_node_id],
                child_node_ids,
                group_name_by_output_id,
                0
            )
            logging.info(f"S2V: group: {group_name}, nodes: {group_info.get_orig_node_ids_count()}")

        return by_group_name

    def add_orig_node_ids(
        self,
        prompt,
        children,
        child_node_ids,
        group_name_by_output_id,
        depth
    ):
        for child_id in (children["in"] + children["out"]):
            must_be_group = group_name_by_output_id[child_id] if child_id in group_name_by_output_id else None

            class_type = prompt[child_id]["class_type"]
            if (
                (depth > 0 and
                    class_type == "Spreadsheet2VideoInputImage"
                ) or
                class_type == "Spreadsheet2Video" or
                (must_be_group is not None and must_be_group != self.group_name)
            ):
                pass
            elif (child_id not in self.orig_node_ids):
                self.orig_node_ids[child_id] = True

                if child_id in child_node_ids:
                    self.add_orig_node_ids(
                        prompt,
                        child_node_ids[child_id],
                        child_node_ids,
                        group_name_by_output_id,
                        depth+1
                    )

    def get_orig_node_ids_count(self):
        return len(self.orig_node_ids.keys())

    def copy_nodes(self, prompt, graph):
        contained = self.orig_node_ids.keys()

        node_id_map = {}
        for node_id in contained:
            original_node = prompt[node_id]
            new_node = graph.node(original_node["class_type"])
            new_node.set_override_display_id(node_id)
            node_id_map[node_id] = (original_node, new_node)

        for node_id in contained:
            (original_node, new_node) = node_id_map[node_id]
            self.copy_node_inputs(node_id, original_node, node_id_map)
        self.node_id_map = node_id_map
        return node_id_map

    def get_new_node(self, output_id):
        (_output_original_node, output_new_node) = self.node_id_map[output_id]
        return output_new_node

    def copy_node_inputs(self, original_node_id, original_node, node_id_map):
        """
        Args:
            original_node_id: id of original node
            original_node: the original node
            node_id_map: map from original_node_id to (original_node, new_node)
        """
        (input_original_node, input_new_node) = node_id_map[original_node_id]
        for k, v in original_node["inputs"].items():
            if is_link(v):
                from_output_node_id = v[0]

                if self.first_input_node_id  == from_output_node_id:
                    input_new_node.set_input(k, [from_output_node_id, v[1]])
                    continue  # ignore: first link.  Handled by link_to_new_input_node

                if from_output_node_id not in node_id_map:
                    print(f"copy_node_inputs: Huh? {from_output_node_id} not in node_id_map.  From node:{original_node_id}")
                    continue

                (output_original_node, output_new_node) = node_id_map[from_output_node_id]
                input_new_node.set_input(k, [output_new_node.id, v[1]])
            else:
                input_new_node.set_input(k, v)

    # convert node input type from string to int, float, boolean
    def convert_new_node_input_value(self, node_class, key, val):
        input_types = node_class.INPUT_TYPES()
        input_type = None
        if "required" in input_types:
            input_type = input_types["required"].get(key)
        if input_type is None and "optional" in input_types:
            input_type = input_types["optional"].get(key)

        if input_type is not None:
            if(input_type[0] == "INT"):
                val = int(val)
            elif(input_type[0] == "FLOAT"):
                val = float(val)
            elif(input_type[0] == "BOOLEAN"):
                val = val.lower().strip() in ("yes", "true", "t", "1")
        return val


    def link_to_new_input_node(
        self, graph, link_to_input, row
    ):
        foundImageInput = False
        for node_id in graph.nodes.keys():
            node = graph.nodes.get(node_id)

            class_type = node.class_type
            if class_type in NODE_CLASS_MAPPINGS:
                node_class = NODE_CLASS_MAPPINGS[class_type]

            node_inputs = node.inputs
            for k, v in node_inputs.items():
                if is_link(v):
                    if v[0] == self.first_input_node_id:
                        if v[1] == 0:
                            # link to image
                            node_inputs[k] = link_to_input
                            foundImageInput = True
                        else:
                            # replace link with row value
                            if v[1] < len(row):
                                node_inputs[k]= self.convert_new_node_input_value(node_class, k, row[v[1]])
                            else:
                                logging.warn(f"S2V: not enough columns in row, column: {v[1]}, row: {','.join(row)}")
        return foundImageInput


class Spreadsheet2VideoFinalVideo(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="Spreadsheet2VideoFinalVideo",
            display_name="Internal S2V Final Video",
            description="internal node, ignore",
            category="S2V Internal",
            inputs=[
                io.Int.Input("previous"),
#                io.Image.Input("images"),
            ],
            outputs=[
                io.Image.Output(),
                io.Audio.Output(),
            ],
            hidden=[],
        )

    @classmethod
    def execute(cls, previous) -> io.NodeOutput:
        # TODO: ffmpeg to save memory?
        all_files = S2VComfy.get_all_files("v_")
        output_images = []
        for file in all_files:
            image = Image.open(file)

            if image.mode == 'I':
                image = image.point(lambda i: i * (1 / 255))
            image = image.convert("RGB")

            image = np.array(image).astype(np.float32) / 255.0
            image = torch.from_numpy(image)[None,]
            output_images.append(image)


        errors = []
        if len(output_images) > 0:
            first_shape = output_images[0].shape
            nth = 0
            for output_image in output_images:
                shape = output_image.shape
                if (
                    shape[1] != first_shape[1] or
                    shape[2] != first_shape[2]
                ):
                    err = f'S2V: All images must be the same size.  This output: {output_image.shape}, nth image:{nth}, first output:{first_shape}'
                    logging.error(err)
                    logging.error('Some subgraphs / workflows use various "resize" nodes that change the output.')
                    logging.error('Put a resize node before S2VOutputImage to resize it back.')
                    errors.append(err)
                nth += 1

        if len(errors) > 0:
            raise Exception("\n".join(errors))

        logging.info(f"S2V: final image count:{len(output_images)}")
        if len(output_images)==0:
            output_tensor = torch.tensor([])
        else:
            output_tensor = torch.cat(output_images, dim=0)

        all_audio_files = S2VComfy.get_all_files("a_")
        output_audio = {}
        waveforms = []
        for audio_file in all_audio_files:
            waveform, sample_rate = torchaudio.load(audio_file)
            waveforms.append(waveform)
            if "sample_rate" in output_audio:
                previous_sample_rate = output_audio["sample_rate"]
                if previous_sample_rate != sample_rate:
                    logging.error(f"S2V: audio has a different sample_rate: previous:{previous_sample_rate} != current:{sample_rate}, {audio_file}")
            else:
                output_audio["sample_rate"] = sample_rate

        if len(waveforms)==0:
            output_audio["waveform"] = torch.empty(1, 1, 0)
        else:
            output_audio["waveform"] = torch.cat(waveforms, dim=1).unsqueeze(0)

        return io.NodeOutput(
            output_tensor,
            output_audio
        )

class Spreadsheet2VideoMultiplySpreadsheet(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="Spreadsheet2VideoMultiplySpreadsheet",
            display_name="Spreadsheet2Video Multiply Spreadsheet",
            category="Spreadsheet2Video",
            description="Adds columns to a spreadsheet.  Duplicating it by the spreadsheet_to_add",
            search_aliases=["spreadsheet", "loop", "multiply", "load", "column"],
            inputs=[
                io.String.Input("spreadsheet", multiline=True, tooltip="Comma separated values with a header row. Can use Spreadsheet2Video Load Spreadsheet node."),
                io.String.Input("spreadsheet_to_add", multiline=True, tooltip="Comma separated values with a header row.  The columns to add"),
            ],
            outputs=[
                io.String.Output(),
            ],
        )

    @classmethod
    def execute(cls, spreadsheet, spreadsheet_to_add) -> io.NodeOutput:
        f = StringIO(spreadsheet)
        reader = csv.reader(f, delimiter=',')
        headerRow = next(reader)
        from_rows = list(reader)

        for from_row in from_rows:
            if len(from_row) < len(headerRow):
                from_row += [None] * (len(headerRow) - len(from_row))


        f = StringIO(spreadsheet_to_add)
        reader = csv.reader(f, delimiter=',')

        output = StringIO()
        writer = csv.writer(output)

        addHeaderRow = next(reader)
        writer.writerow(headerRow + addHeaderRow)

        for row_to_add in reader:
            for from_row in from_rows:
                writer.writerow(from_row + row_to_add)
        # writer.close()

        return io.NodeOutput(
            output.getvalue()
            )


class Spreadsheet2VideoLoadText(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        input_path = Path(folder_paths.get_input_directory())
        input_dirs = [
            "",
            "csv"
        ]

        options = []
        for input_dir in input_dirs:
            input_full_dir = input_path / input_dir
            if input_full_dir.is_dir():
                input_short_dir = Path(input_dir)
                for d in input_full_dir.iterdir():
                    options.append(str(input_short_dir / d.name))


        # files = folder_paths.filter_files_content_types(files, ["text", "application"])
        return io.Schema(
            node_id="Spreadsheet2VideoLoadText",
            display_name="Spreadsheet2Video Load Spreadsheet",
            category="Spreadsheet2Video",
            description="Loads spreadsheet or .csv into text for input into main Spreadsheet2Video node",
            search_aliases=["spreadsheet", "loop", "output", "load", "csv", "xlsx", "ods"],
            inputs=[
                io.Combo.Input("text_file", options=options),
                io.String.Input("sheet_name", default="", tooltip="Leave blank for first sheet", optional=True),
            ],
            outputs=[
                io.String.Output(),
            ],
        )

    @classmethod
    def ods_to_csv(cls, ods_path: str, sheet_name):
        """Convert all sheets in an ODS file to separate CSV files."""
        ods_path = Path(ods_path)

        # Read all sheets from the ODS file
        df = pd.read_excel(ods_path, sheet_name)

        buffer = StringIO()
        df.to_csv(buffer, index=False)
        return io.NodeOutput(
            buffer.getvalue()
        )

    @classmethod
    def execute(cls, text_file, sheet_name=None) -> io.NodeOutput:
        input_dir = folder_paths.get_input_directory()
        text_file_path = Path(input_dir) / text_file
        if (text_file_path.suffix == '.csv'
            or text_file_path.suffix == '.csv'
        ):
            return io.NodeOutput(
                text_file_path.read_text(encoding='utf-8')
            )
        else:
            if sheet_name == "" or sheet_name is None:
                sheet_name = 0
            return cls.ods_to_csv(str(text_file_path), sheet_name)

    @classmethod
    def fingerprint_inputs(s, text_file, sheet_name=None):
        input_dir = folder_paths.get_input_directory()
        text_file_path = Path(input_dir) / text_file
        st=Path(text_file_path).stat()
        
        stat_str = "\n".join([
            text_file,
            f"{st.st_size}",
            f"{st.st_mtime}",
            str(sheet_name)
        ])

        # Hash it
        return hashlib.md5(stat_str.encode()).hexdigest()



class Spreadsheet2VideoNode(io.ComfyNode):
    """
    An example node

    Class methods
    -------------
    define_schema (io.Schema):
        Tell the main program the metadata, input, output parameters of nodes.
    fingerprint_inputs:
        optional method to control when the node is re executed.
    check_lazy_status:
        optional method to control list of input names that need to be evaluated.

    """
    blank_image_shape=[1,1,1,1]

    @classmethod
    def define_schema(cls) -> io.Schema:
        """
            Return a schema which contains all information about the node.
            Some types: "Model", "Vae", "Clip", "Conditioning", "Latent", "Image", "Int", "String", "Float", "Combo".
            For outputs the "io.Model.Output" should be used, for inputs the "io.Model.Input" can be used.
            The type can be a "Combo" - this will be a list for selection.
        """
        return io.Schema(
            node_id="Spreadsheet2Video",
            display_name="Spreadsheet2Video",
            category="Spreadsheet2Video",
            search_aliases=["spreadsheet", "loop", "output"],
            inputs=[
                io.String.Input("spreadsheet", multiline=True, tooltip="Comma separated values with a header row. Can use Spreadsheet2Video Load Spreadsheet node."),
                io.Image.Input("first_image", optional=True, tooltip="First image to send to the S2VInputImage node.  Use EmptyImage if you don't need it"),
            ],
            outputs=[
                io.Image.Output(),
                io.Audio.Output(),
            ],
            hidden=[io.Hidden.unique_id, io.Hidden.dynprompt, io.Hidden.prompt],
            enable_expand=True,
            is_output_node=True,
        )

    @classmethod
    def check_lazy_status(cls, spreadsheet="", first_image=None):
        return []

    @classmethod
    def execute(cls, spreadsheet="", first_image=None) -> io.NodeOutput:
        global last_processed_time
        last_processed_time = None

        graph = GraphBuilder()

        # Use StringIO to treat the string as a file
        f = StringIO(spreadsheet)

        by_group_name = GroupInfo.map_outputs(cls.hidden.prompt)


        reader = csv.reader(f, delimiter=',')
        headerRow = next(reader) # skip header

        processImageNode = graph.node("Spreadsheet2VideoProcessImage",
            previous = 1, images = first_image)
        lastProcessImageNode = processImageNode

        rows_done = 0
        for row in reader:
            if(len(headerRow) < len(row)):
                logging.warn(
                    "S2V: csv header is not long enough for row: header:{}, row:{}, {}".format(
                    len(headerRow), len(row), " , ".join(row)
                ))

            previous_image_output = processImageNode.out(1)

            name = row[0].strip()
            if name == "":
                logging.error(f"S2V: No : {row}")
                continue
            if name not in by_group_name:
                raise ValueError(f"S2V: Could not find Spreadsheet2VideoInputImage node with name: {name}")
                continue

            group_info = by_group_name[name]
            group_info.copy_nodes(cls.hidden.prompt, graph)
            processImageNode = group_info.change_out_node(graph)
            if processImageNode is None:
                processImageNode = graph.node('Spreadsheet2VideoProcessImage')

            if previous_image_output is not None:
                link_to_input = previous_image_output
            else:
                link_to_input = first_image

            if lastProcessImageNode:
                processImageNode.set_input(
                    "previous",
                    lastProcessImageNode.out(0)
                )
            lastProcessImageNode = processImageNode

            foundImageInput = group_info.link_to_new_input_node(
                graph,
                link_to_input,
                row
                )
            if not foundImageInput:
                logging.warn(f"S2V: No image input node, ignore if this is a non image workflow, column1: {name}")



            previous_image_output = group_info.output_image_link
            rows_done += 1

        if rows_done == 0:
            logging.error("S2V: No rows done, did you put in a header row?")

        finalVideoNode = graph.node(
            "Spreadsheet2VideoFinalVideo",
            previous = lastProcessImageNode.out(0)
        )

        return io.NodeOutput(
            finalVideoNode.out(0),
            finalVideoNode.out(1),
            expand=graph.finalize(),
            )


    """
        The node will always be re executed if any of the inputs change but
        this method can be used to force the node to execute again even when the inputs don't change.
        You can make this node return a number or a string. This value will be compared to the one returned the last time the node was
        executed, if it is different the node will be executed again.
        This method is used in the core repo for the LoadImage node where they return the image hash as a string, if the image hash
        changes between executions the LoadImage node is executed again.
    """
    @classmethod
    def fingerprint_inputs(s, spreadsheet="", first_image=None):
        # always run because the other nodes are not a part of this execution pth
        return str(random.random())


