# FlickerTag_CD
I could not find any existing apps to efficiently but manually tag large amounts of image patches for change detection purposes.

This is a lightweight PyQT GUI to annotate image patches for object level change detection data in remote sensing.
Note that this interface is best used on small image patches that have already been co-registered.
There is no zoom or panning functionality as it is not intended to be used on very large images.

## Installation

 - Clone the repo.
 - Make a conda environment from the provided yaml.
 - Run flicker_tag_cd.py in the environment.

## Usage

**Manual mode**

For if you want to manually select image pairs. Slow, but more flexible.
 - Select "Manual mode" from the initial pop-up.
 - Define the change classes you want to tag, with their corresponding colors.
 - Select "Start manual"

**Automatic mode**

For if you want the interface to load up image pairs for you. Fast, but assumes a specific file naming scheme.
 - Make sure the "Automatic mode parameters" at the top of the script are set up how you like it.
 - Select "Automatic mode" from the initial pop-up.

To find matching image pairs, the GUI will:
 - Go through your reference file directory (global_a_dir) and find all files containing a reference tag (a_tag).
 - Go through your target file directory (global_b_dir) and find all files containing a target tag (b_tag).
 - Two images are regarded a match if they are identical except for a_tag or b_tag in a specific position.

**Output format**

The output of the tagging operation is a pickle file that contains a list of two-value tuples, each representing a polygon.
 - A list of points representing a polygon as defined withing the image plane of the reference image.
 - A string defining what class the relevant polygon belongs to.

If the annotator selects "Skip" for a comparison, then the pickle will only contain a string "skipped by annotator".

## Contact details

tiantheunissen@gmail.com

Feedback welcome!

[flickertag_short_demo.webm](https://github.com/user-attachments/assets/82cedf3e-0018-4f63-a997-187fbcd74984)



