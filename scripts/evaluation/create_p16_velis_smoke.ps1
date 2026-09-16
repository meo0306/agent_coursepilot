param(
    [Parameter(Mandatory = $true)]
    [string]$TemplatePath,
    [Parameter(Mandatory = $true)]
    [string]$CandidatePath,
    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$msoFalse = 0
$msoTrue = -1
$ppSaveAsOpenXMLPresentation = 24
$ppPlaceholderTitle = 1
$ppPlaceholderBody = 2
$ppPlaceholderCenterTitle = 3
$ppPlaceholderSubtitle = 4
$ppPlaceholderObject = 7
$ppPlaceholderPicture = 18

function Limit-SmokeText {
    param([string]$Text, [int]$Maximum = 84)
    $normalized = ($Text -replace "\s+", " ").Trim()
    if ($normalized.Length -le $Maximum) {
        return $normalized
    }
    return $normalized.Substring(0, $Maximum - 3) + "..."
}

$candidate = Get-Content -Raw -Encoding utf8 -LiteralPath $CandidatePath | ConvertFrom-Json
$deck = $candidate.cases | Where-Object { $_.record_id -eq "p16-ds3-transformer" }
if ($null -eq $deck) {
    throw "Transformer P16 case is missing from $CandidatePath"
}

$smokePlan = @(
    @{ slide = 1; layout = "Presentation Title" },
    @{ slide = 2; layout = "Title and Content" },
    @{ slide = 4; layout = "Section Title" },
    @{ slide = 6; layout = "Two Columns" },
    @{ slide = 7; layout = "Two Columns" },
    @{ slide = 8; layout = "Two Columns, Picture Right" },
    @{ slide = 18; layout = "One Picture" },
    @{ slide = 23; layout = "Close" }
)

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$powerPoint = New-Object -ComObject PowerPoint.Application
$presentation = $null
try {
    # Untitled=true creates a presentation from the POTX while preserving its masters/layouts.
    $presentation = $powerPoint.Presentations.Open($TemplatePath, $msoFalse, $msoTrue, $msoFalse)
    if ($presentation.Designs.Count -lt 1) {
        throw "Velis template exposes no PowerPoint Design"
    }

    while ($presentation.Slides.Count -gt 0) {
        $presentation.Slides.Item(1).Delete()
    }

    $design = $presentation.Designs.Item($presentation.Designs.Count)
    $layouts = @{}
    for ($index = 1; $index -le $design.SlideMaster.CustomLayouts.Count; $index++) {
        $layout = $design.SlideMaster.CustomLayouts.Item($index)
        $layouts[$layout.Name] = $layout
    }

    foreach ($planItem in $smokePlan) {
        if (-not $layouts.ContainsKey($planItem.layout)) {
            throw "Required Velis layout is missing: $($planItem.layout)"
        }
        $target = $deck.slide_targets | Where-Object { $_.slide_index -eq $planItem.slide }
        if ($null -eq $target) {
            throw "Slide target $($planItem.slide) is missing"
        }

        $targetTitle = [string]$target.title_intent
        $knowledgePointNames = @(
            $target.knowledge_point_snapshots |
                ForEach-Object { Limit-SmokeText -Text ([string]$_.canonical_name) -Maximum 48 }
        )
        $claimLines = @(
            $target.required_claims |
                ForEach-Object { Limit-SmokeText -Text ([string]$_) -Maximum 84 }
        )
        if ($claimLines.Count -eq 0) {
            $claimLines = $knowledgePointNames
        }
        if ($claimLines.Count -eq 0) {
            $claimLines = @($targetTitle)
        }
        $bodySegments = @($claimLines | Select-Object -First 3)

        $slide = $presentation.Slides.AddSlide(
            $presentation.Slides.Count + 1,
            $layouts[$planItem.layout]
        )
        $titleWritten = $false
        $bodyWritten = 0

        for ($shapeIndex = 1; $shapeIndex -le $slide.Shapes.Placeholders.Count; $shapeIndex++) {
            $shape = $slide.Shapes.Placeholders.Item($shapeIndex)
            $placeholderType = $shape.PlaceholderFormat.Type
            if (($placeholderType -eq $ppPlaceholderTitle -or $placeholderType -eq $ppPlaceholderCenterTitle) -and -not $titleWritten) {
                $shape.TextFrame.TextRange.Text = $targetTitle
                $titleWritten = $true
            }
            elseif (($placeholderType -eq $ppPlaceholderSubtitle -or $placeholderType -eq $ppPlaceholderBody -or $placeholderType -eq $ppPlaceholderObject) -and $planItem.layout -ne "Close") {
                if ($bodyWritten -lt $bodySegments.Count) {
                    $shape.TextFrame.TextRange.Text = $bodySegments[$bodyWritten]
                    $bodyWritten++
                }
            }
            elseif ($placeholderType -eq $ppPlaceholderPicture) {
                $shape.AlternativeText = "教师替换图片占位符；P16 烟测保留为可编辑 Placeholder"
            }
        }

        if (-not $titleWritten) {
            $titleBox = $slide.Shapes.AddTextbox(1, 54, 34, 620, 54)
            $titleBox.TextFrame.TextRange.Text = $targetTitle
            $titleBox.TextFrame.TextRange.Font.Size = 28
        }
        if ($bodyWritten -eq 0 -and $planItem.layout -ne "Close") {
            $bodyBox = $slide.Shapes.AddTextbox(1, 64, 130, 600, 300)
            $bodyBox.TextFrame.TextRange.Text = ($bodySegments -join "`r`n")
            $bodyBox.TextFrame.TextRange.Font.Size = 18
        }

        $citationText = "Gold Slide Target $($target.slide_id) | Evidence: " + (($target.evidence_ids | Select-Object -First 2) -join ", ")
        $citation = $slide.Shapes.AddTextbox(1, 40, 510, 620, 24)
        $citation.TextFrame.TextRange.Text = $citationText
        $citation.TextFrame.TextRange.Font.Size = 8

        $notesText = "[Sources]`r`n" + (($target.evidence_snapshots | ForEach-Object { "Evidence $($_.evidence_id): $($_.gold_text)" }) -join "`r`n")
        for ($noteIndex = 1; $noteIndex -le $slide.NotesPage.Shapes.Placeholders.Count; $noteIndex++) {
            $noteShape = $slide.NotesPage.Shapes.Placeholders.Item($noteIndex)
            if ($noteShape.PlaceholderFormat.Type -eq $ppPlaceholderBody) {
                $noteShape.TextFrame.TextRange.Text = $notesText
                break
            }
        }
    }

    $presentation.SaveAs($OutputPath, $ppSaveAsOpenXMLPresentation)
}
finally {
    if ($null -ne $presentation) {
        $presentation.Close()
        [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($presentation) | Out-Null
    }
    $powerPoint.Quit()
    [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($powerPoint) | Out-Null
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

Write-Output $OutputPath
