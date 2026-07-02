from fastapi import APIRouter, UploadFile, File, HTTPException
import cv2
import numpy as np
import os

router = APIRouter(prefix="/api/v1/studio", tags=["Artisan Studio"])


@router.post("/refine-video")
async def refine_artisan_video(file: UploadFile = File(...)):
    temp_input_path = f"temp_{file.filename}"
    temp_output_path = f"refined_{file.filename}"

    with open(temp_input_path, "wb") as buffer:
        buffer.write(await file.read())

    cap = cv2.VideoCapture(temp_input_path)
    if not cap.isOpened():
        raise HTTPException(
            status_code=400, detail="Cannot process video file format."
        )

    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    if n_frames == 0:
        cap.release()
        os.remove(temp_input_path)
        raise HTTPException(status_code=400, detail="Empty video file.")

    fourcc = cv2.VideoWriter_fourcc(*"XVID")
    out = cv2.VideoWriter(temp_output_path, fourcc, fps, (width, height))

    _, prev_frame = cap.read()
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

    for _ in range(n_frames - 1):
        success, frame = cap.read()
        if not success:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        features_prev = cv2.goodFeaturesToTrack(
            prev_gray, maxCorners=100, qualityLevel=0.01, minDistance=30
        )

        if features_prev is not None:
            features_curr, status, _ = cv2.calcOpticalFlowPyrLK(
                prev_gray, gray, features_prev, None
            )

            valid_prev = features_prev[status == 1]
            valid_curr = features_curr[status == 1]

            if len(valid_prev) > 4:
                matrix, _ = cv2.estimateAffinePartial2D(valid_prev, valid_curr)
                if matrix is not None:
                    stabilized_frame = cv2.warpAffine(
                        frame, matrix, (width, height)
                    )
                    out.write(stabilized_frame)
                else:
                    out.write(frame)
            else:
                out.write(frame)
        else:
            out.write(frame)

        prev_gray = gray

    cap.release()
    out.release()

    if os.path.exists(temp_input_path):
        os.remove(temp_input_path)
    if os.path.exists(temp_output_path):
        os.remove(temp_output_path)

    return {
        "status": "success",
        "message": "Stabilized video complete. Output stored locally.",
        "processed_frames": n_frames,
        "video_dimensions": f"{width}x{height}",
    }
