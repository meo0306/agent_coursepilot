#!/usr/bin/env bash
set -euo pipefail

workspace=/workspace
render_root="${P16_RENDER_ROOT:-$workspace/storage_eval/p16_render_work}"
sources=(
  "$workspace/resources/templates/exporters/ppt_standard_lecture_v1.pptx"
  "$workspace/resources/templates/exporters/ppt_concept_explanation_v1.pptx"
  "$workspace/resources/templates/exporters/ppt_case_seminar_v1.pptx"
  "$render_root/velis-smoke-8slides.pptx"
)

for pass_name in pass1 pass2; do
  output_dir="$render_root/$pass_name"
  profile_dir="/tmp/p16-$pass_name"
  mkdir -p "$output_dir"
  soffice \
    "-env:UserInstallation=file://$profile_dir" \
    --headless \
    --convert-to pdf \
    --outdir "$output_dir" \
    "${sources[@]}"
  for pdf_path in "$output_dir"/*.pdf; do
    page_dir="${pdf_path%.pdf}_pages"
    mkdir -p "$page_dir"
    pdftoppm -png -r 120 "$pdf_path" "$page_dir/slide"
  done
done

soffice --version
pdftoppm -v 2>&1 | head -1
