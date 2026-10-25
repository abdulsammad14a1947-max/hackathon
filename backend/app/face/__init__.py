"""Face verification engine package (M10 camera attendance).

Server-side detection + matching: YuNet detector and SFace recognizer ONNX
models executed through OpenCV's DNN module. Models are sha256-pinned and
fetched once with ``python -m app.face.models``.
"""
