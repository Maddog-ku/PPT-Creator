export type TemplateId = "editorial" | "midnight" | "paper";

export type SlideData = {
  id: string;
  eyebrow: string;
  title: string;
  body: string;
  kind:
    | "cover"
    | "section"
    | "cards"
    | "split"
    | "metric"
    | "comparison"
    | "roadmap"
    | "quote"
    | "closing";
  visual_prompt?: string | null;
  image_data?: string | null;
};

const themes = {
  editorial: {
    background: "FFF7F1",
    surface: "FFFFFF",
    text: "271521",
    muted: "725F69",
    accent: "E9468C",
    accentSoft: "FAD8E7",
    line: "E9D6DF",
  },
  midnight: {
    background: "101423",
    surface: "1B2236",
    text: "F7F8FC",
    muted: "B7BED1",
    accent: "58D6C7",
    accentSoft: "203F45",
    line: "35405A",
  },
  paper: {
    background: "F4F0E6",
    surface: "FBF8F1",
    text: "26251F",
    muted: "6D695D",
    accent: "B14A32",
    accentSoft: "E9D7CB",
    line: "D8D0C0",
  },
} as const;

function pointsFrom(body: string, count = 3): string[] {
  const points = body
    .split(/[。！？；\n]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, count);
  while (points.length < count) points.push(points.at(-1) ?? body);
  return points;
}

function metricFrom(title: string, body: string): string {
  return `${title} ${body}`.match(/\d[\d,.]*\s*(?:%|×|x|倍)?/i)?.[0]?.trim() ?? "01";
}

export async function buildPresentationPptx(
  topic: string,
  slides: SlideData[],
  template: TemplateId,
): Promise<Blob> {
  const { default: PptxGenJS } = await import("pptxgenjs");
  const pptx = new PptxGenJS();
  const theme = themes[template];
  const font = "Noto Sans CJK TC";
  pptx.layout = "LAYOUT_WIDE";
  pptx.author = "PPT Creator";
  pptx.company = "PPT Creator";
  pptx.subject = topic;
  pptx.title = topic;
  pptx.theme = {
    headFontFace: font,
    bodyFontFace: font,
  };

  slides.forEach((item, index) => {
    const slide = pptx.addSlide();
    const title = item.title;
    const points = pointsFrom(item.body);
    slide.background = { color: theme.background };

    slide.addText("PPT CREATOR", {
      x: 0.6, y: 0.28, w: 2.8, h: 0.28,
      fontFace: font, fontSize: 9, bold: true, color: theme.accent, charSpacing: 2,
      margin: 0,
    });
    slide.addShape(pptx.ShapeType.line, {
      x: 0.6, y: 6.9, w: 12.1, h: 0,
      line: { color: theme.line, width: 1 },
    });
    slide.addText(String(index + 1).padStart(2, "0"), {
      x: 11.8, y: 6.98, w: 0.9, h: 0.24,
      fontFace: font, fontSize: 9, color: theme.muted, align: "right", margin: 0,
    });

    if (item.kind === "cover") {
      slide.addShape(pptx.ShapeType.rect, {
        x: 9.7, y: 0, w: 3.63, h: 7.5,
        fill: { color: theme.accent }, line: { color: theme.accent },
      });
      slide.addShape(pptx.ShapeType.ellipse, {
        x: 9.15, y: 0.95, w: 2.3, h: 2.3,
        fill: { color: theme.accentSoft, transparency: 15 },
        line: { color: theme.accentSoft, transparency: 100 },
      });
      slide.addText(item.eyebrow, {
        x: 0.75, y: 1.05, w: 4, h: 0.3,
        fontFace: font, fontSize: 12, bold: true, color: theme.accent, charSpacing: 1.4, margin: 0,
      });
      slide.addText(title, {
        x: 0.72, y: 1.65, w: 8.2, h: 2.15,
        fontFace: font, fontSize: title.length > 34 ? 38 : 48, bold: true,
        color: theme.text, margin: 0, breakLine: false, valign: "middle",
      });
      slide.addText(item.body, {
        x: 0.76, y: 4.28, w: 6.8, h: 0.95,
        fontFace: font, fontSize: 18, color: theme.muted, margin: 0, breakLine: false,
      });
    } else if (item.kind === "section") {
      slide.addShape(pptx.ShapeType.rect, {
        x: 0, y: 0, w: 4.25, h: 7.5,
        fill: { color: theme.accent }, line: { color: theme.accent },
      });
      slide.addText(String(index + 1).padStart(2, "0"), {
        x: 0.45, y: 2.15, w: 3.2, h: 1.8,
        fontFace: font, fontSize: 76, bold: true, color: "FFFFFF", margin: 0,
        align: "center", valign: "middle", breakLine: false,
      });
      slide.addText(item.eyebrow, {
        x: 4.9, y: 1.45, w: 5.4, h: 0.3,
        fontFace: font, fontSize: 11, bold: true, color: theme.accent,
        charSpacing: 1.4, margin: 0,
      });
      slide.addText(title, {
        x: 4.85, y: 2.02, w: 7.25, h: 1.55,
        fontFace: font, fontSize: title.length > 32 ? 34 : 43, bold: true,
        color: theme.text, margin: 0, breakLine: false, valign: "middle",
      });
      slide.addShape(pptx.ShapeType.line, {
        x: 4.9, y: 3.93, w: 1.0, h: 0,
        line: { color: theme.accent, width: 4 },
      });
      slide.addText(item.body, {
        x: 4.9, y: 4.25, w: 6.65, h: 1.15,
        fontFace: font, fontSize: 17, color: theme.muted, margin: 0,
        breakLine: false,
      });
      [0.58, 0.92, 1.28].forEach((height, stripeIndex) => {
        slide.addShape(pptx.ShapeType.rect, {
          x: 11.45 + stripeIndex * 0.32, y: 6.15 - height, w: 0.13, h: height,
          fill: { color: theme.accent, transparency: 25 + stripeIndex * 20 },
          line: { color: theme.accent, transparency: 100 },
        });
      });
    } else if (item.kind === "cards") {
      slide.addText(item.eyebrow, {
        x: 0.72, y: 0.92, w: 4, h: 0.3,
        fontFace: font, fontSize: 11, bold: true, color: theme.accent, charSpacing: 1.2, margin: 0,
      });
      slide.addText(title, {
        x: 0.7, y: 1.28, w: item.image_data ? 7.55 : 11.8, h: 0.85,
        fontFace: font, fontSize: title.length > 35 ? 30 : 36, bold: true, color: theme.text, margin: 0,
      });
      if (item.image_data) {
        slide.addImage({ data: item.image_data, x: 8.72, y: 0.72, w: 3.9, h: 1.62 });
      }
      const cardLayouts = index % 3 === 1
        ? [
            { x: 0.72, y: 2.42, w: 4.65, h: 3.18 },
            { x: 5.65, y: 2.72, w: 3.18, h: 2.88 },
            { x: 9.1, y: 3.02, w: 3.18, h: 2.58 },
          ]
        : [0, 1, 2].map((pointIndex) => ({
            x: 0.72 + pointIndex * 4.12,
            y: index % 3 === 2 ? 2.42 + pointIndex * 0.28 : 2.55,
            w: 3.72,
            h: index % 3 === 2 ? 3.12 - pointIndex * 0.14 : 2.95,
          }));
      points.forEach((point, pointIndex) => {
        const layout = cardLayouts[pointIndex];
        const featured = index % 3 === 1 && pointIndex === 0;
        slide.addShape(pptx.ShapeType.roundRect, {
          ...layout, rectRadius: 0.07,
          fill: { color: featured ? theme.accent : theme.surface },
          line: { color: featured ? theme.accent : theme.line, width: 1.2 },
        });
        slide.addText(`0${pointIndex + 1}`, {
          x: layout.x + 0.28, y: layout.y + 0.28, w: 0.6, h: 0.3,
          fontFace: font, fontSize: 12, bold: true,
          color: featured ? "FFFFFF" : theme.accent, margin: 0,
        });
        slide.addText(["核心洞察", "關鍵訊號", "下一步"][pointIndex], {
          x: layout.x + 0.28, y: layout.y + 0.84, w: layout.w - 0.56, h: 0.42,
          fontFace: font, fontSize: 18, bold: true,
          color: featured ? "FFFFFF" : theme.text, margin: 0,
        });
        slide.addText(point, {
          x: layout.x + 0.28, y: layout.y + 1.5, w: layout.w - 0.56, h: layout.h - 1.77,
          fontFace: font, fontSize: featured ? 16 : 14,
          color: featured ? "FFF0F7" : theme.muted, margin: 0.02, breakLine: false,
        });
      });
    } else if (item.kind === "split") {
      slide.addShape(pptx.ShapeType.rect, {
        x: 7.58, y: 0, w: 5.75, h: 7.5,
        fill: { color: theme.accentSoft }, line: { color: theme.accentSoft },
      });
      slide.addText(item.eyebrow, {
        x: 0.72, y: 1.03, w: 4, h: 0.3,
        fontFace: font, fontSize: 11, bold: true, color: theme.accent,
        charSpacing: 1.2, margin: 0,
      });
      slide.addText(title, {
        x: 0.7, y: 1.48, w: 6.15, h: 1.4,
        fontFace: font, fontSize: title.length > 32 ? 30 : 38, bold: true,
        color: theme.text, margin: 0, breakLine: false,
      });
      slide.addText(item.body, {
        x: 0.72, y: 3.35, w: 5.9, h: 1.35,
        fontFace: font, fontSize: 17, color: theme.muted, margin: 0,
        breakLine: false,
      });
      if (item.image_data) {
        slide.addImage({ data: item.image_data, x: 7.98, y: 0.72, w: 4.78, h: 6.06 });
      } else {
        slide.addText("FOCUS", {
          x: 8.08, y: 1.12, w: 1.2, h: 0.25,
          fontFace: font, fontSize: 9, bold: true, color: theme.accent,
          charSpacing: 1.4, margin: 0,
        });
        slide.addText(points[0], {
          x: 8.05, y: 1.65, w: 4.35, h: 1.25,
          fontFace: font, fontSize: 22, bold: true, color: theme.text,
          margin: 0, breakLine: false,
        });
        points.slice(1).forEach((point, pointIndex) => {
          slide.addShape(pptx.ShapeType.line, {
            x: 8.08, y: 3.45 + pointIndex * 1.18, w: 4.15, h: 0,
            line: { color: theme.line, width: 1 },
          });
          slide.addText(String(pointIndex + 2).padStart(2, "0"), {
            x: 8.08, y: 3.66 + pointIndex * 1.18, w: 0.42, h: 0.26,
            fontFace: font, fontSize: 10, bold: true, color: theme.accent, margin: 0,
          });
          slide.addText(point, {
            x: 8.68, y: 3.62 + pointIndex * 1.18, w: 3.55, h: 0.62,
            fontFace: font, fontSize: 13, color: theme.muted, margin: 0,
          });
        });
      }
    } else if (item.kind === "metric") {
      slide.addText(item.eyebrow, {
        x: 0.72, y: 0.92, w: 4, h: 0.3,
        fontFace: font, fontSize: 11, bold: true, color: theme.accent, margin: 0,
      });
      slide.addText(title, {
        x: 0.7, y: 1.38, w: item.image_data ? 6.5 : 7.1, h: 1.28,
        fontFace: font, fontSize: title.length > 34 ? 29 : 36, bold: true, color: theme.text, margin: 0,
      });
      slide.addText(item.body, {
        x: 0.72, y: 3.02, w: item.image_data ? 5.8 : 6.3, h: 1.35,
        fontFace: font, fontSize: 17, color: theme.muted, margin: 0, breakLine: false,
      });
      if (item.image_data) {
        slide.addImage({ data: item.image_data, x: 7.65, y: 1.08, w: 4.95, h: 4.95 });
      } else {
        slide.addShape(pptx.ShapeType.roundRect, {
          x: 8.35, y: 1.25, w: 3.65, h: 3.85, rectRadius: 0.08,
          fill: { color: theme.accentSoft }, line: { color: theme.accentSoft },
        });
        slide.addText(metricFrom(item.title, item.body), {
          x: 8.68, y: 2.03, w: 3, h: 1,
          fontFace: font, fontSize: 49, bold: true, color: theme.accent, align: "center", margin: 0,
        });
        slide.addText(points[0], {
          x: 8.7, y: 3.23, w: 3, h: 0.55,
          fontFace: font, fontSize: 16, bold: true, color: theme.text, align: "center", margin: 0,
        });
      }
    } else if (item.kind === "comparison") {
      slide.addText(item.eyebrow, {
        x: 0.72, y: 0.92, w: 4, h: 0.3,
        fontFace: font, fontSize: 11, bold: true, color: theme.accent,
        charSpacing: 1.2, margin: 0,
      });
      slide.addText(title, {
        x: 0.7, y: 1.35, w: 11.4, h: 0.88,
        fontFace: font, fontSize: title.length > 38 ? 29 : 36, bold: true,
        color: theme.text, margin: 0,
      });
      [
        { label: "BEFORE", heading: "現況", point: points[0], x: 0.72, featured: false },
        { label: "AFTER", heading: "方向", point: points[1], x: 6.72, featured: true },
      ].forEach((column) => {
        slide.addShape(pptx.ShapeType.roundRect, {
          x: column.x, y: 2.62, w: 5.6, h: 2.65, rectRadius: 0.06,
          fill: { color: column.featured ? theme.accentSoft : theme.surface },
          line: { color: column.featured ? theme.accent : theme.line, width: 1.2 },
        });
        slide.addText(column.label, {
          x: column.x + 0.36, y: 2.93, w: 1.15, h: 0.24,
          fontFace: font, fontSize: 9, bold: true, color: theme.accent,
          charSpacing: 1.2, margin: 0,
        });
        slide.addText(column.heading, {
          x: column.x + 0.36, y: 3.4, w: 2.4, h: 0.42,
          fontFace: font, fontSize: 20, bold: true, color: theme.text, margin: 0,
        });
        slide.addText(column.point, {
          x: column.x + 0.36, y: 4.05, w: 4.82, h: 0.82,
          fontFace: font, fontSize: 14, color: theme.muted, margin: 0,
          breakLine: false,
        });
      });
      slide.addShape(pptx.ShapeType.ellipse, {
        x: 6.22, y: 3.58, w: 0.62, h: 0.62,
        fill: { color: theme.accent }, line: { color: theme.accent },
      });
      slide.addText("→", {
        x: 6.22, y: 3.69, w: 0.62, h: 0.25,
        fontFace: font, fontSize: 13, bold: true, color: "FFFFFF",
        align: "center", margin: 0,
      });
      slide.addText(points[2], {
        x: 6.72, y: 5.63, w: 5.55, h: 0.5,
        fontFace: font, fontSize: 12, italic: true, color: theme.muted,
        align: "right", margin: 0,
      });
    } else if (item.kind === "roadmap") {
      slide.addText(item.eyebrow, {
        x: 0.72, y: 0.92, w: 4, h: 0.3,
        fontFace: font, fontSize: 11, bold: true, color: theme.accent, margin: 0,
      });
      slide.addText(title, {
        x: 0.7, y: 1.35, w: item.image_data ? 7.55 : 11.5, h: 1.0,
        fontFace: font, fontSize: title.length > 35 ? 30 : 36, bold: true, color: theme.text, margin: 0,
      });
      if (item.image_data) {
        slide.addImage({ data: item.image_data, x: 8.72, y: 0.72, w: 3.9, h: 1.62 });
      }
      if (index % 3 !== 1) {
        slide.addShape(pptx.ShapeType.line, {
          x: 1.25, y: 3.44, w: 10.65, h: 0,
          line: { color: theme.line, width: index % 3 === 2 ? 5 : 3 },
        });
      }
      points.forEach((point, pointIndex) => {
        const x = 1.0 + pointIndex * 4.15;
        const stepY = index % 3 === 1 ? 3.38 - pointIndex * 0.35 : 3.08;
        if (index % 3 === 1) {
          slide.addShape(pptx.ShapeType.roundRect, {
            x: x - 0.12, y: stepY - 0.28, w: 3.35, h: 2.42,
            rectRadius: 0.05,
            fill: { color: pointIndex === 2 ? theme.accentSoft : theme.surface },
            line: { color: pointIndex === 2 ? theme.accent : theme.line, width: 1.1 },
          });
        }
        slide.addShape(pptx.ShapeType.ellipse, {
          x, y: stepY, w: 0.72, h: 0.72,
          fill: { color: theme.accent }, line: { color: theme.accent },
        });
        slide.addText(String(pointIndex + 1), {
          x, y: stepY + 0.14, w: 0.72, h: 0.28,
          fontFace: font, fontSize: 13, bold: true, color: "FFFFFF", align: "center", margin: 0,
        });
        slide.addText(["第一階段", "第二階段", "第三階段"][pointIndex], {
          x: x - 0.05, y: stepY + 0.96, w: 2.9, h: 0.42,
          fontFace: font, fontSize: 18, bold: true, color: theme.text, margin: 0,
        });
        slide.addText(point, {
          x: x - 0.05, y: stepY + 1.48, w: 3.02, h: 0.74,
          fontFace: font, fontSize: 14, color: theme.muted, margin: 0, breakLine: false,
        });
      });
    } else if (item.kind === "quote") {
      slide.addShape(pptx.ShapeType.rect, {
        x: 0, y: 0, w: 8.15, h: 7.5,
        fill: { color: theme.accent }, line: { color: theme.accent },
      });
      slide.addShape(pptx.ShapeType.rect, {
        x: 8.15, y: 0, w: 5.18, h: 7.5,
        fill: { color: theme.accentSoft }, line: { color: theme.accentSoft },
      });
      slide.addText("“", {
        x: 9.02, y: 0.78, w: 3.3, h: 2.35,
        fontFace: "Georgia", fontSize: 112, bold: true, color: theme.accent,
        align: "center", margin: 0,
      });
      slide.addText(item.eyebrow, {
        x: 0.78, y: 1.05, w: 4.4, h: 0.3,
        fontFace: font, fontSize: 11, bold: true, color: "FFE6F0",
        charSpacing: 1.3, margin: 0,
      });
      slide.addText(title, {
        x: 0.76, y: 1.73, w: 10.45, h: 1.82,
        fontFace: font, fontSize: title.length > 42 ? 32 : 41, bold: true,
        color: "FFFFFF", margin: 0, breakLine: false,
      });
      slide.addShape(pptx.ShapeType.line, {
        x: 0.82, y: 4.12, w: 0, h: 1.05,
        line: { color: "FB923C", width: 4 },
      });
      slide.addText(item.body, {
        x: 1.08, y: 4.08, w: 6.35, h: 1.12,
        fontFace: font, fontSize: 17, color: "FFE3EE", margin: 0,
        breakLine: false,
      });
    } else {
      slide.addShape(pptx.ShapeType.ellipse, {
        x: 4.73, y: 0.85, w: 3.9, h: 3.9,
        fill: { color: theme.accentSoft }, line: { color: theme.accentSoft, transparency: 100 },
      });
      slide.addText(item.eyebrow, {
        x: 4.15, y: 1.28, w: 5, h: 0.32,
        fontFace: font, fontSize: 11, bold: true, color: theme.accent, align: "center", margin: 0,
      });
      slide.addText(title, {
        x: 1.6, y: 2.0, w: 10.1, h: 1.2,
        fontFace: font, fontSize: title.length > 35 ? 33 : 42, bold: true, color: theme.text,
        align: "center", margin: 0,
      });
      slide.addText(item.body, {
        x: 3.05, y: 3.65, w: 7.2, h: 0.9,
        fontFace: font, fontSize: 17, color: theme.muted, align: "center", margin: 0,
      });
    }
  });

  const data = await pptx.write({ outputType: "arraybuffer", compression: true });
  return new Blob([data as ArrayBuffer], {
    type: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  });
}
