# AURA computer-vision capability

Manual annotation does not require computer-vision dependencies. When
OpenCV (`opencv-python`) is separately installed, managed video metadata
extraction can report dimensions, frames per second, and approximate
duration. Frame sampling is bounded by `AURA_FRAME_SAMPLE_LIMIT` and returns
timestamp/dimension metadata, not persisted image previews.

OpenCV is not a declared required dependency. Unsupported codecs or unreadable
files yield partial metadata rather than blocking manual annotation. Browser
playback also depends on codec support.

Object detection is not implemented. `AURA_VISION_ENABLED`,
`AURA_VISION_MODEL`, and `AURA_VISION_WEIGHTS_PATH` do not cause model
downloads. A configured local model file is not sufficient: the API reports
that no inference adapter exists and does not fabricate detections.

Videos stay in the configured managed media directory. No cloud CV service is
used.
