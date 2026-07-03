import os

import cv2


class MediaGenerator:
    def __init__(self):
        self.tts_engine = None

    def stabilize_video(self, input_path: str, output_path: str = None) -> dict:
        if output_path is None:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_stabilized{ext}"

        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            return {"status": "error", "message": "Cannot open video file."}

        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)

        if n_frames == 0:
            cap.release()
            return {"status": "error", "message": "Empty video file."}

        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

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
                        stabilized = cv2.warpAffine(frame, matrix, (width, height))
                        out.write(stabilized)
                    else:
                        out.write(frame)
                else:
                    out.write(frame)
            else:
                out.write(frame)

            prev_gray = gray

        cap.release()
        out.release()

        return {
            "status": "success",
            "output_path": output_path,
            "processed_frames": n_frames,
        }
