import React from "react";
import {Img, staticFile} from "remotion";

interface Props {
  /** Canvas pixel coordinate of the marker's real contact point. */
  tipX: number;
  tipY: number;
  scale?: number;
}

const HAND_WIDTH = 282;
const HAND_HEIGHT = 282;
const PEN_TIP_X = 198;
const PEN_TIP_Y = 197;

/**
 * The source hand is alpha-cropped during asset preparation. Its marker tip
 * is the cropped image's top-left pixel, matching the reference renderer's
 * tip-anchor convention.
 */
export const HandPen: React.FC<Props> = ({tipX, tipY, scale = 1}) => {
  const width = HAND_WIDTH * scale;
  const height = HAND_HEIGHT * scale;
  return (
    <div
      style={{
        position: "absolute",
        left: tipX - PEN_TIP_X * scale,
        top: tipY - PEN_TIP_Y * scale,
        width,
        height,
        pointerEvents: "none",
        zIndex: 20,
      }}
    >
      <Img
        src={staticFile("hand-real-pen.png")}
        style={{width, height, display: "block"}}
      />
    </div>
  );
};
