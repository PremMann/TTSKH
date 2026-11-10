import Foundation
import AVFoundation
import Vision

// Arguments: <videoPath> <outJsonPath> [yMin] [yMax] [startSec] [endSec]
let args = CommandLine.arguments
guard args.count >= 3 else {
    print("Usage: swift auto_extract_timeline.swift <videoPath> <outJsonPath> [yMin] [yMax] [startSec] [endSec]")
    exit(1)
}

let videoPath = args[1]
let outJson = args[2]

let asset = AVURLAsset(url: URL(fileURLWithPath: videoPath))
let gen = AVAssetImageGenerator(asset: asset)
gen.appliesPreferredTrackTransform = true
gen.requestedTimeToleranceBefore = .zero
gen.requestedTimeToleranceAfter = .zero

let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.recognitionLanguages = ["zh-Hans", "zh-Hant"]

// Step 1: Detect Subtitle Y-Band if not provided
var yMin: Double = args.count >= 4 ? Double(args[3])! : 0.0
var yMax: Double = args.count >= 5 ? Double(args[4])! : 0.0

if yMin == 0.0 || yMax == 0.0 {
    print("Auto-detecting subtitle vertical band across test frames...")
    var detectedYs: [Double] = []
    var sampleH: Double = 854.0

    for fraction in [0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95] {
        let testT = CMTimeGetSeconds(asset.duration) * fraction
        let cmTime = CMTime(seconds: testT, preferredTimescale: 600)
        guard let cgImg = try? gen.copyCGImage(at: cmTime, actualTime: nil) else { continue }
        let h = Double(cgImg.height)
        sampleH = h
        let handler = VNImageRequestHandler(cgImage: cgImg, options: [:])
        try? handler.perform([req])
        for obs in req.results ?? [] {
            guard let cand = obs.topCandidates(1).first else { continue }
            let box = obs.boundingBox
            let topDownY = (1.0 - box.origin.y - box.height) * h
            let boxH = box.height * h
            // Look dynamically in lower half (55% to 92% of height)
            if topDownY > (h * 0.55) && topDownY < (h * 0.92) && boxH >= (h * 0.02) && boxH <= (h * 0.10) {
                let s = cand.string.trimmingCharacters(in: .whitespacesAndNewlines)
                if s.count >= 1 {
                    detectedYs.append(topDownY)
                }
            }
        }
    }
    
    if detectedYs.isEmpty {
        print("Warning: Could not auto-detect subtitle band. Using default lower third.")
        yMin = sampleH * 0.68
        yMax = sampleH * 0.88
    } else {
        detectedYs.sort()
        let medianY = detectedYs[detectedYs.count / 2]
        // Expand safety margin around median subtitle band
        yMin = max(sampleH * 0.55, medianY - (sampleH * 0.06))
        yMax = min(sampleH * 0.95, medianY + (sampleH * 0.10))
        print(String(format: "Auto-detected subtitle band: %.1f .. %.1f (median: %.1f, frameH: %.0f)", yMin, yMax, medianY, sampleH))
    }
} else {
    print(String(format: "Using specified subtitle band: %.1f .. %.1f", yMin, yMax))
}

struct VisualSub {
    var text: String
    var start: Double
    var end: Double
}

var rawFrames: [(t: Double, text: String)] = []
let step = 0.25
let assetDur = CMTimeGetSeconds(asset.duration)
let startT = args.count >= 6 ? Double(args[5])! : 0.0
let maxT = args.count >= 7 ? Double(args[6])! : (assetDur.isFinite && assetDur > 0 ? assetDur : 300.0)

print(String(format: "Scanning video frames %.1fs -> %.1fs (step: %.2fs)...", startT, maxT, step))
for t in stride(from: startT, to: maxT, by: step) {
    let cmTime = CMTime(seconds: t, preferredTimescale: 600)
    let cgImg: CGImage
    do { cgImg = try gen.copyCGImage(at: cmTime, actualTime: nil) } catch {
        if t >= maxT - 1.0 || t >= assetDur - 1.0 { break }
        continue
    }
    let h = Double(cgImg.height)
    let handler = VNImageRequestHandler(cgImage: cgImg, options: [:])
    do { try handler.perform([req]) } catch { fputs("Vision OCR failed: \(error)\n", stderr); exit(2) }
    
    var sub = ""
    for obs in req.results ?? [] {
        guard let cand = obs.topCandidates(1).first else { continue }
        let box = obs.boundingBox
        let topDownY = (1.0 - box.origin.y - box.height) * h
        if topDownY >= yMin && topDownY <= yMax {
            let s = cand.string.trimmingCharacters(in: .whitespacesAndNewlines)
            if !s.isEmpty && s.count >= 1 {
                sub = s
                break
            }
        }
    }
    rawFrames.append((t: t, text: sub))
    if Int(t * 4) % 100 == 0 {
        print(String(format: "Progress: %.1fs / %.1fs", t, maxT))
    }
}

// Group contiguous frames
var groupedSubs: [VisualSub] = []
var curText = ""
var curStart = 0.0
var curEnd = 0.0

func cleanText(_ s: String) -> String {
    return s.replacingOccurrences(of: " ", with: "")
            .replacingOccurrences(of: "，", with: "")
            .replacingOccurrences(of: "。", with: "")
            .replacingOccurrences(of: "！", with: "")
            .replacingOccurrences(of: "？", with: "")
}

func isSimilar(_ a: String, _ b: String) -> Bool {
    let ca = cleanText(a)
    let cb = cleanText(b)
    if ca == cb { return true }

    return false
}

for item in rawFrames {
    if item.text.isEmpty {
        if !curText.isEmpty {
            groupedSubs.append(VisualSub(text: curText, start: curStart, end: min(curEnd + step, maxT)))
            curText = ""
        }
    } else {
        if curText.isEmpty {
            curText = item.text
            curStart = item.t
            curEnd = item.t
        } else if isSimilar(curText, item.text) {
            if item.text.count > curText.count {
                curText = item.text
            }
            curEnd = item.t
        } else {
            groupedSubs.append(VisualSub(text: curText, start: curStart, end: min(curEnd + step, maxT)))
            curText = item.text
            curStart = item.t
            curEnd = item.t
        }
    }
}

if !curText.isEmpty {
    groupedSubs.append(VisualSub(text: curText, start: curStart, end: min(curEnd + step, maxT)))
}

// Filter out noise segments < 0.4s with 1 char
var cleanSubs: [VisualSub] = []
for sub in groupedSubs {
    let dur = sub.end - sub.start
    if dur <= 0 { continue }
    cleanSubs.append(sub)
}

print("\nDetected \(cleanSubs.count) visual subtitle cues!")

var outputList: [[String: Any]] = []
for (i, sub) in cleanSubs.enumerated() {
    outputList.append([
        "id": i + 1,
        "start": sub.start,
        "end": sub.end,
        "duration": sub.end - sub.start,
        "chinese": sub.text
    ])
}

let jsonData = try! JSONSerialization.data(withJSONObject: outputList, options: .prettyPrinted)
try! jsonData.write(to: URL(fileURLWithPath: outJson))
print("Saved to \(outJson)")

// Report the detected band in the padded portrait render canvas.
if let image = try? gen.copyCGImage(at: CMTime(seconds: startT, preferredTimescale: 600), actualTime: nil) {
    let scale = min(1080.0 / Double(image.width), 1920.0 / Double(image.height))
    let pad = (1920.0 - Double(image.height) * scale) / 2.0
    let top = max(0, Int((pad + yMin * scale - 20) / 2) * 2)
    let bottom = min(1920, Int((pad + yMax * scale + 60) / 2) * 2)
    let band: [String: Int] = ["y": top, "height": max(2, bottom - top)]
    if let data = try? JSONSerialization.data(withJSONObject: band) {
        try? data.write(to: URL(fileURLWithPath: outJson + ".band.json"))
    }
}
