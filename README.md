
Use a spreadsheet as input for ComfyUI execution.

![Nodes](docs/imgs/Spreadsheet2Video\_nodes.png)



## Examples

[example\_workflows](example_workflows/)

Or in manager -> templates -> Spreadsheet2Video


## Instructions

* Make a spreadsheet with the first column as the name of the part of the workflow you want to execute for that row. Put a header row in the spreadsheet.
* Use the "Spreadsheet2Video Input Image" and "Spreadsheet2Video Output Image" nodes to specify which part of the workflow you want to execute.  You can have as many of these as you want but they must be separate, cannot depend on each other to run.
* Link up an image to the main Spreadsheet2Video node
* Row 1 will use the first image.  Row 2 will use the image output from Row 1.  If row 1 outputs a video, row 2 will get the last frame of video from row 1.

Can be used for non-video workflows.  See the example workflow in the templates.

[Video Instructions](https://www.youtube.com/watch?v=2c_Ass5-dg4)


### Long video

[Long video workflow](example_workflows/Spreadsheet2Video_ConcatVideo.json)

The video was made with the workflow and panning was done later in a video editor.

<div align="center">
  <video src="https://github.com/user-attachments/assets/656c2f7e-081c-45e1-8e7d-dcef2ee018e2" width="70%" poster=""> </video>
</div>



### Comparison video

* [Comparison video workflow](example_workflows/Spreadsheet2Video_Comparison.json)

<div align="center">
  <video src="https://github.com/user-attachments/assets/65fc85b0-d24f-4f4e-9f52-6c23aa54d115" width="50%" poster=""> </video>
</div>


### Deforum-like videos example

* [Make zoom / rotate / move parameters with a game controller](https://niknah.github.io/spreadsheet2video-ComfyUI/deforum\_maker.html)
* Copy and paste into a .csv file. [example .csv file](example_workflows/Cooking.csv)
* [workflow](example_workflows/Spreadsheet2Video_deforum.json)

<div align="center">
  <video src="https://github.com/user-attachments/assets/c95a9386-ebfc-4830-955b-374493fbc69f" width="50%" poster=""> </video>
</div>


### Non video

* [Audio workflow](example_workflows/Spreadsheet2Video_NonVideo.json)









## Nodes

| Node | Description |
| -- | -- |
| Spreadsheet2Video | Use a start image or use EmptyImage node if you don't want to make a video |
| Spreadsheet2Video Input Image | Give it a name. Link the columns to your workflow. |
| Spreadsheet2Video Output Image | Put the output image here.  Link the image to the `Spreadsheet2Video Input Image` node if you have no image output.  The next row will use this image or the last frame if it is a video. |
| Spreadsheet2Video Load Spreadsheet | Optional.  Loads a file, link to spreadsheet when you want to use a .csv, xlsx, ods file instead of typing in the data.  Can put the file into `input` or `input/csv` folders. |
| Spreadsheet2Video Multiply Spreadsheet | Adds extra columns to a spreadsheet. Multiplying the spreadsheet. |
| Other nodes | Ignore them.  Used internally only |


* The raw frames are in the `ComfyUI/temp` folder if you want lossless quality


## Warning

* The preview might not open the workflow in in the assets list.  You need to download the file and open the file instead.

* To load .ods spreadsheets.  Run `pip install odfpy`.

* When you set the seed to "randomize".  The number only changes after every run.  It will be the same seed after each row.  Add another column and connect it up to the seed to get a different seed every row.

## Changes

* v1.0.1: Allow running of non-video workflows without using a blank image or video output.  Added multiply spreadsheet node.
