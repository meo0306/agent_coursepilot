import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const repoRoot = path.resolve(process.cwd(), "../..");
const outputDir = path.join(repoRoot, "resources", "templates", "exporters");
const qaDir = path.join(process.cwd(), "qa");

async function writeBlob(target, blob) {
  await fs.writeFile(target, new Uint8Array(await blob.arrayBuffer()));
}

function addText(slide, name, text, position, style) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name,
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = style;
  return shape;
}

async function buildDeck(stem, eyebrow, title, subtitle, accent) {
  const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });
  const slide = presentation.slides.add();
  slide.background.fill = "#F5F7FA";
  slide.shapes.add({
    geometry: "rect",
    name: "accent-rail",
    position: { left: 0, top: 0, width: 22, height: 720 },
    fill: accent,
    line: { style: "solid", fill: accent, width: 0 },
  });
  addText(slide, "eyebrow", eyebrow, { left: 76, top: 64, width: 720, height: 30 }, {
    fontSize: 15, bold: true, color: "#65768A", fontFamily: "Microsoft YaHei",
  });
  addText(slide, "title", title, { left: 76, top: 136, width: 1080, height: 96 }, {
    fontSize: 48, bold: true, color: "#25384B", fontFamily: "Microsoft YaHei",
  });
  addText(slide, "subtitle", subtitle, { left: 76, top: 246, width: 980, height: 72 }, {
    fontSize: 22, color: "#526579", fontFamily: "Microsoft YaHei",
  });
  slide.shapes.add({
    geometry: "line",
    name: "content-rule",
    position: { left: 76, top: 362, width: 1128, height: 0 },
    line: { style: "solid", fill: "#CBD5E1", width: 1 },
  });
  addText(slide, "content-placeholder", "{{ editable_content }}", { left: 76, top: 400, width: 1060, height: 116 }, {
    fontSize: 24, color: "#384B5E", fontFamily: "Microsoft YaHei",
  });
  addText(slide, "footer", "CoursePilot · editable template v1", { left: 76, top: 652, width: 500, height: 26 }, {
    fontSize: 13, color: "#7B8B9D", fontFamily: "Microsoft YaHei",
  });
  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(path.join(outputDir, `${stem}.pptx`));
  await writeBlob(path.join(qaDir, `${stem}.png`), await presentation.export({ slide, format: "png", scale: 1 }));
  await fs.writeFile(path.join(qaDir, `${stem}.layout.json`), await (await slide.export({ format: "layout" })).text());
}

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(qaDir, { recursive: true });
await buildDeck("ppt_standard_lecture_v1", "STANDARD LECTURE", "{{ lecture_title }}", "{{ learning_focus }}", "#2563EB");
await buildDeck("ppt_concept_explanation_v1", "CONCEPT EXPLANATION", "{{ concept_name }}", "{{ concept_definition }}", "#0F766E");
await buildDeck("ppt_case_seminar_v1", "CASE SEMINAR", "{{ case_title }}", "{{ guiding_question }}", "#7C3AED");
