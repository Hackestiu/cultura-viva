import cv2
from datetime import datetime
from loguru import logger

# ==========================================
# CONFIGURATION
# ==========================================
# Options: "KEYBOARD" or "BUTTON"
TRIGGER_MODE = "KEYBOARD"
SAVE_DIR = "."
RESIZE_FOR_MOBILENET = True
MOBILENET_INPUT_SIZE = (224, 224)

# Initialize RPC bridge globally ONLY if using button mode
bridge = None
if TRIGGER_MODE == "BUTTON":
    from arduino_rpc import Bridge
    bridge = Bridge()


# ==========================================
# TRIGGER FUNCTION ABSTRACTION
# ==========================================
def is_triggered(key: int) -> bool:
    """Checks a single poll for a trigger event. `key` is the preview window keypress."""
    if TRIGGER_MODE == "KEYBOARD":
        return key in (13, 32)  # ENTER or SPACE

    elif TRIGGER_MODE == "BUTTON":
        return bridge.available() and bridge.read() == "TRIGGER_CAPTURE"

    return False


# ==========================================
# MAIN CAPTURE LOOP
# ==========================================
def main():
    logger.info(f"Starting camera preview in {TRIGGER_MODE} mode.")
    logger.info("[SPACE]/[ENTER] to capture a picture, [Q] to quit.")
    cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
    if not cap.isOpened():
        logger.error("Could not open camera device.")
        return

    window_name = "Camera Preview"

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.warning("Failed to capture frame from stream.")
                continue

            cv2.imshow(window_name, frame)
            key = cv2.waitKey(1) & 0xFF

            if key == ord('q'):
                break

            if is_triggered(key):
                # Flush buffer and snatch freshest frame
                for _ in range(5):
                    cap.grab()
                ret, frame = cap.retrieve()

                if not ret:
                    logger.warning("Failed to capture frame from stream.")
                    continue

                if RESIZE_FOR_MOBILENET:
                    frame = cv2.resize(frame, MOBILENET_INPUT_SIZE, interpolation=cv2.INTER_AREA)

                height, width = frame.shape[:2]
                filename = f"{SAVE_DIR}/capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                cv2.imwrite(filename, frame)
                logger.info(f"--> Saved picture to {filename} ({width}x{height})")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        logger.info("Camera released. Exiting.")


if __name__ == "__main__":
    main()
