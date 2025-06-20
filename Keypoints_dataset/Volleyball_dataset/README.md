# Volleyball Dataset Keypoint Extraction with HRNet

This repository contains code and resources for extracting keypoint data (e.g., joint locations) from the **Volleyball Dataset** and **Volleyball Tracking Annotation Dataset** using HRNet (High-Resolution Network), a state-of-the-art model for human pose estimation. The datasets are sourced from [mostafa-saad/deep-activity-rec](https://github.com/mostafa-saad/deep-activity-rec), associated with the paper "A Hierarchical Deep Temporal Model for Group Activity Recognition" (CVPR 2016).

## Project Overview
The goal is to process video frames from the Volleyball Dataset, use the provided bounding box annotations to localize players, and apply HRNet to extract keypoints (e.g., shoulders, elbows, knees) for action recognition and player tracking in volleyball videos.

## Volleyball Dataset Summary

### Dataset Structure
- **Total Videos**: 55 videos, each with a unique ID (0 to 54).
- **Train Videos** (24): IDs 1, 3, 6, 7, 10, 13, 15, 16, 18, 22, 23, 31, 32, 36, 38, 39, 40, 41, 42, 48, 50, 52, 53, 54.
- **Validation Videos** (15): IDs 0, 2, 8, 12, 17, 19, 24, 26, 27, 28, 30, 33, 46, 49, 51.
- **Test Videos** (16): IDs 4, 5, 9, 11, 14, 20, 21, 25, 29, 34, 35, 37, 43, 44, 45, 47.

### Frame Annotations
- Each video has directories (e.g., `volleyball/39/29885`) containing 41 frames per annotated frame:
  - 20 frames before, 1 target frame, 20 frames after (e.g., for frame 29885, window = 29865 to 29905).
  - **Note**: Scenes change rapidly in volleyball, so frames outside this window are typically not representative. A smaller window of 5 frames before and 4 frames after the target frame is often used for analysis.

### Annotations File
- Each video directory contains an `annotations.txt` file with lines formatted as:

{Frame ID} {Frame Activity Class} {Player Annotation} {Player Annotation} ...

- **Player Annotation Format**: `{Action Class} X Y W H` (bounding box coordinates for each player).

### Video Resolutions
- **1920x1080**: Videos 2, 37, 38, 39, 40, 41, 44, 45 (8 videos).
- **1280x720**: All other videos (47 videos).

## Volleyball Tracking Annotation Dataset Summary

### Structure
- Organized into directories named `seq01`, `seq02`, etc., each corresponding to a sequence.
- Each sequence directory contains a subdirectory named after the **middle frame** (e.g., `seq01/3595`).
- Inside this subdirectory, a `.txt` file (e.g., `3595.txt`) contains bounding box annotations for a 21-frame window:
- 10 frames before, the middle frame, and 9 frames after.
- Example: For middle frame 29885, annotations cover frames 29875 to 29895.

### Annotation Format
Each line in the `.txt` file follows this format:

{Player ID} {X_min} {Y_min} {X_max} {Y_max} {Frame ID} {Flag 1} {Flag 2} {Flag 3} {Action Class}

- **Player ID**: Unique identifier for each player (e.g., 0, 1, ..., 10).
- **X_min, Y_min, X_max, Y_max**: Bounding box coordinates (top-left and bottom-right corners).
- **Frame ID**: Frame number (e.g., 3586 to 3605).
- **Unknown Flags (3)**: Three binary flags (0 or 1). Possible meanings include:
  - Visibility, occlusion, or tracking confidence.
  - Team affiliation or role (e.g., attacker vs. defender).
  - Consult dataset documentation or analyze patterns to confirm their purpose.
- **Action Class**: Player’s action (e.g., `digging`, `standing`).

## Repository Structure
- `data/`: Placeholder for dataset files (not included due to size; download from the original source).
- `scripts/`: Python scripts for parsing annotations, extracting frames, and analysis.
- `notebooks/`: Jupyter notebooks for exploratory data analysis and visualization.
- `models/`: Placeholder for trained models (to be added based on your experiments).

## Getting Started
1. **Download the Dataset**: Obtain the volleyball dataset and tracking annotations from their respective sources.
2. **Parse Annotations**: Use scripts in the `scripts/` directory to process `annotations.txt` and tracking `.txt` files.
3. **Run Analysis**: Explore the data using notebooks in the `notebooks/` directory.
4. **Contribute**: Add your own scripts, models, or visualizations to the repository.

## License
 Volleyball Dataset and tracking annotations are sourced from [mostafa-saad/deep-activity-rec](https://github.com/mostafa-saad/deep-activity-rec).[](https://github.com/mostafa-saad/deep-activity-rec/blob/master/README.md)
- Please cite the following if using the extended dataset:
  ```bibtex
  @inproceedings{msibrahiCVPR16deepactivity,
    author = {Mostafa S. Ibrahim and Srikanth Muralidharan and Zhiwei Deng and Arash Vahdat and Greg Mori},
    title = {A Hierarchical Deep Temporal Model for Group Activity Recognition},
    booktitle = {2016 IEEE Conference on Computer Vision and Pattern Recognition (CVPR)},
    year = {2016}
  }

# Volleyball Tracking Annotation Processor

## Overview

This script processes the Volleyball Tracking Annotation Dataset, which contains bounding box annotations for volleyball game sequences. The script reads the dataset, organizes the bounding box data into a nested dictionary, and saves it to a `.pkl` file for further use (e.g., in group activity recognition tasks).

The dataset is structured as `seq_id/middle_frame/middle_frame.txt`, where:
- `seq_id` is the sequence identifier (e.g., `0`, `1`, `3`, etc.).
- `middle_frame` is the middle frame number of a sequence (e.g., `24730`).
- `middle_frame.txt` contains bounding box annotations for 20 frames: 10 frames before the middle frame, the middle frame itself, and 9 frames after.

The script ensures that sequences and middle frames are processed in ascending order.
## Usage

1. **Set the Dataset Path**:
   - Update the `dataset_path` in the `main` function to point to your dataset directory.
   - Example: `dataset_path = "/path/to/volleyball_tracking_annotation/"`

2. **Run the Script**:
   ```bash
   python volleyball_bbox.py
   
## Output File Data Format

The script saves the processed data to a `.pkl` file (e.g., `volleyball_bboxes.pkl`) using the `pickle` module. The output data is structured as a nested dictionary with the following format:

```python
{
    seq_id (int): {
        middle_frame (int): {
            frame_id (int): np.array([[x_min, y_min, x_max, y_max], ...], dtype=np.int32)
        }
    }
}
```

# Volleyball Dataset Keypoint Extraction

This script processes the **Volleyball dataset** to extract 2D pose keypoints using a pre-trained **HRNet model** from [MMPose](https://github.com/open-mmlab/mmpose). It uses existing bounding box annotations to perform pose estimation and saves the output as a `.pkl` file.

---

🧠 Model Used
-Model: HRNet-W32
-Dataset: COCO 2D keypoints
-Config File: td-hm_hrnet-w32_8xb64-210e_coco-256x192.py
-Weights File: hrnet_w32_coco_256x192.pth

🚀 How to Run
```
python pose_extraction.py
```
This will:

Load bounding boxes from volleyball_bboxes.pkl

Use a 10-frame window around each middle frame

Run pose estimation on each frame

Save keypoints in volleyball_keypoints.pkl

📦 Output Format
The output is a nested dictionary saved as a pickle file:

```
{
    video_id: {
        target_frame: {
            frame_id: np.ndarray of shape (12, 17, 3)  # 12 people, 17 keypoints, (x, y, confidence)
        }
    }
}
```
-video_id: Integer identifier of the video
-target_frame: Middle frame of a 10-frame window
-frame_id: Frame number in that window
=keypoints: Numpy array with (x, y, score) for each of 17 COCO keypoints per person

If fewer than 12 people are detected, zero-padding is applied





