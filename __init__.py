from typing_extensions import override

from comfy_api.latest import ComfyExtension, io
from .Spreadsheet2VideoNodes import (
        Spreadsheet2VideoNode,
        Spreadsheet2VideoInputImage,
        Spreadsheet2VideoOutputImage,
        Spreadsheet2VideoProcessImage,
        Spreadsheet2VideoFinalVideo,
        Spreadsheet2VideoLoadText,
        Spreadsheet2VideoSequence,
        Spreadsheet2VideoFilesList,
        Spreadsheet2VideoMultiplySpreadsheet
    )



# Set the web directory, any .js file in that directory will be loaded by the frontend as a frontend extension
WEB_DIRECTORY = "./js"


# Add custom API routes, using router
#from aiohttp import web
#from server import PromptServer
#
#@PromptServer.instance.routes.get("/hello")
#async def get_hello(request):
#    return web.json_response("hello")


class Spreadsheet2VideoExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            Spreadsheet2VideoNode,
            Spreadsheet2VideoInputImage,
            Spreadsheet2VideoOutputImage,
            Spreadsheet2VideoProcessImage,
            Spreadsheet2VideoFinalVideo,
            Spreadsheet2VideoLoadText,
            Spreadsheet2VideoSequence,
            Spreadsheet2VideoFilesList,
            Spreadsheet2VideoMultiplySpreadsheet,
        ]


async def comfy_entrypoint() -> Spreadsheet2VideoExtension:  # ComfyUI calls this to load your extension and its nodes.
    return Spreadsheet2VideoExtension()
