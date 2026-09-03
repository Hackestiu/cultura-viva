#pragma once

#include <Arduino.h>
#include "../core/config.h"

extern uint8_t camFrameBuf[CAM_TOTAL_PIXELS * 2];
extern bool newCameraFrameFlag;

/**
 * Decodes a Base64 encoded string into a raw byte buffer.
 *
 * @param input        Base64 ASCII string.
 * @param output       Destination byte array buffer.
 * @param maxOutputLen Maximum output capacity of the destination buffer.
 * @return Number of decoded bytes written to output.
 */
int base64Decode(const String &input, uint8_t *output, int maxOutputLen);

/**
 * Processes an incoming camera frame chunk sent via RPC from Python.
 *
 * @param chunkIndex   Zero-based index of the received chunk.
 * @param totalChunks Total number of expected chunks per frame.
 * @param data        Base64-encoded chunk data.
 */
void receive_camera_chunk(int chunkIndex, int totalChunks, String data);

/**
 * Renders a placeholder frame on the display when camera mode is active but awaiting live frames.
 */
void drawCameraViewPlaceholder();

/**
 * Draws the assembled RGB565 thumbnail frame onto the display.
 */
void drawCameraFrame();

/**
 * Draws the "Are you sure of this photo?" confirmation footer banner.
 */
void drawPhotoConfirmationOverlay();

/**
 * Draws the warning alert box when attempting to record without taking/confirming a photo first.
 */
void drawNoPhotoWarningOverlay();

