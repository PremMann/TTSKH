import Foundation
import Cocoa

// Arguments: <cuesJsonPath> <outPngDir> <yMin> [height] [totalDuration] [width] [height]
let args = CommandLine.arguments
guard args.count >= 4 else {
    print("Usage: swift render_subs_universal.swift <cuesJsonPath> <outPngDir> <yMin> [height] [totalDuration] [canvasWidth] [canvasHeight]")
    exit(1)
}

let jsonPath = args[1]
let outDirUrl = URL(fileURLWithPath: args[2])
let yMin = Double(args[3])!
let subHeight = args.count >= 5 ? Double(args[4])! : 180.0
let totalDur = args.count >= 6 ? Double(args[5])! : 300.0
let width = args.count >= 7 ? Int(args[6])! : 1080
let height = args.count >= 8 ? Int(args[7])! : 1920
let bottomY = Double(height) - (yMin + subHeight)
let scaleFactor = Double(width) / 720.0

try? FileManager.default.createDirectory(at: outDirUrl, withIntermediateDirectories: true)

let paragraphStyle = NSMutableParagraphStyle()
paragraphStyle.alignment = .center
paragraphStyle.lineBreakMode = .byWordWrapping

// 1. Create transparent empty frame
let emptyPath = outDirUrl.appendingPathComponent("empty.png")
if !FileManager.default.fileExists(atPath: emptyPath.path) {
    if let repEmpty = NSBitmapImageRep(
        bitmapDataPlanes: nil,
        pixelsWide: width,
        pixelsHigh: height,
        bitsPerSample: 8,
        samplesPerPixel: 4,
        hasAlpha: true,
        isPlanar: false,
        colorSpaceName: .calibratedRGB,
        bytesPerRow: width * 4,
        bitsPerPixel: 32
    ) {
        if let data = repEmpty.bitmapData {
            memset(data, 0, width * height * 4)
        }
        if let pngEmpty = repEmpty.representation(using: .png, properties: [:]) {
            try? pngEmpty.write(to: emptyPath)
        }
    }
}

// Helper: Extract valid non-empty text from cue
func extractCueText(_ cue: [String: Any]) -> String {
    for key in ["khmer_sub", "khmer_spoken", "khmer"] {
        if let s = cue[key] as? String {
            let trimmed = s.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty && trimmed != "-" && trimmed != "—" && trimmed != "…" && trimmed != "." {
                return trimmed
            }
        }
    }
    return ""
}

// 2. Read cues
guard let data = try? Data(contentsOf: URL(fileURLWithPath: jsonPath)),
      let cues = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] else {
    print("Failed to read JSON cues at \(jsonPath)")
    exit(1)
}

// Check font availability and log warning if primary font missing
let preferredFontName = "Khmer OS Battambang"
let fallbackFontName = "Kantumruy Pro"
if NSFont(name: preferredFontName, size: 30.0) == nil {
    if NSFont(name: fallbackFontName, size: 30.0) != nil {
        print("[WARN] Preferred font '\(preferredFontName)' not found. Falling back to '\(fallbackFontName)'.")
    } else {
        print("[WARN] Neither '\(preferredFontName)' nor '\(fallbackFontName)' found. Falling back to boldSystemFont.")
    }
}

print("Rendering CoreText subtitles for \(cues.count) cues (yMin: \(yMin), bottomY: \(bottomY))...")

let queue = OperationQueue()
queue.maxConcurrentOperationCount = 8

for cue in cues {
    queue.addOperation {
        guard let idx = cue["id"] as? Int else { return }
        let text = extractCueText(cue)
        if text.isEmpty {
            // Non-verbal or empty subtitle cue (e.g. sign or purely instrumental pause)
            return
        }
        let filename = String(format: "cue_%04d.png", idx)
        let cuePath = outDirUrl.appendingPathComponent(filename)
        
        guard let rep = NSBitmapImageRep(
            bitmapDataPlanes: nil,
            pixelsWide: width,
            pixelsHigh: height,
            bitsPerSample: 8,
            samplesPerPixel: 4,
            hasAlpha: true,
            isPlanar: false,
            colorSpaceName: .calibratedRGB,
            bytesPerRow: width * 4,
            bitsPerPixel: 32
        ) else { return }
        
        if let data = rep.bitmapData {
            memset(data, 0, width * height * 4)
        }
        
        NSGraphicsContext.saveGraphicsState()
        guard let context = NSGraphicsContext(bitmapImageRep: rep) else { return }
        NSGraphicsContext.current = context
        let cgCtx = context.cgContext
        
        cgCtx.setAllowsAntialiasing(true)
        cgCtx.setShouldAntialias(true)
        cgCtx.setAllowsFontSmoothing(true)
        cgCtx.setShouldSmoothFonts(true)
        
        // Dynamic font size with overflow guard
        var baseFont: Double = text.count > 75 ? 24.0 : (text.count > 50 ? 28.0 : (text.count > 35 ? 32.0 : 36.0))
        var fontSize: CGFloat = CGFloat(baseFont * scaleFactor)
        var font = NSFont(name: preferredFontName, size: fontSize) 
                ?? NSFont(name: fallbackFontName, size: fontSize)
                ?? NSFont.boldSystemFont(ofSize: fontSize)
        
        let strokeColor = NSColor.black
        let fillColor = NSColor(calibratedRed: 1.0, green: 0.933, blue: 0.149, alpha: 1.0) // Cinema Yellow #FFEE26
        
        let margin = CGFloat(30.0 * scaleFactor)
        let rect = NSRect(x: margin, y: CGFloat(bottomY), width: CGFloat(Double(width) - 2.0 * Double(margin)), height: CGFloat(subHeight))
        
        // Measure text height and shrink if it exceeds box height
        var testAttrs: [NSAttributedString.Key: Any] = [
            .font: font,
            .paragraphStyle: paragraphStyle
        ]
        var bounds = (text as NSString).boundingRect(
            with: NSSize(width: rect.width, height: 1000),
            options: [.usesLineFragmentOrigin, .usesFontLeading],
            attributes: testAttrs
        )
        
        while bounds.height > rect.height - CGFloat(16.0 * scaleFactor) && baseFont > 18.0 {
            baseFont -= 2.0
            fontSize = CGFloat(baseFont * scaleFactor)
            font = NSFont(name: preferredFontName, size: fontSize)
                ?? NSFont(name: fallbackFontName, size: fontSize)
                ?? NSFont.boldSystemFont(ofSize: fontSize)
            testAttrs[.font] = font
            bounds = (text as NSString).boundingRect(
                with: NSSize(width: rect.width, height: 1000),
                options: [.usesLineFragmentOrigin, .usesFontLeading],
                attributes: testAttrs
            )
        }
        
        let centeredY = rect.origin.y + max(0, (rect.height - bounds.height) / 2.0)
        let drawRect = NSRect(x: rect.origin.x, y: centeredY, width: rect.width, height: bounds.height + CGFloat(10.0 * scaleFactor))
        
        // Pass 0: Soft dark translucent backing pill to guarantee 100% masking of Chinese text underneath
        let pillPadX = CGFloat(24.0 * scaleFactor)
        let pillPadY = CGFloat(12.0 * scaleFactor)
        let textWidth = min(rect.width, bounds.width + pillPadX * 2.0)
        let pillX = (Double(width) - Double(textWidth)) / 2.0
        let pillRect = NSRect(x: pillX, y: centeredY - pillPadY / 2.0, width: textWidth, height: bounds.height + pillPadY + CGFloat(10.0 * scaleFactor))
        let pillPath = NSBezierPath(roundedRect: pillRect, xRadius: CGFloat(14.0 * scaleFactor), yRadius: CGFloat(14.0 * scaleFactor))
        NSColor(calibratedWhite: 0.0, alpha: 0.72).setFill()
        pillPath.fill()
        
        // Pass 1: Heavy black outline
        let strokeAttrs: [NSAttributedString.Key: Any] = [
            .font: font,
            .strokeColor: strokeColor,
            .strokeWidth: CGFloat(6.5 * scaleFactor),
            .paragraphStyle: paragraphStyle
        ]
        (text as NSString).draw(in: drawRect, withAttributes: strokeAttrs)
        
        // Pass 2: Sharp yellow text
        let fillAttrs: [NSAttributedString.Key: Any] = [
            .font: font,
            .foregroundColor: fillColor,
            .paragraphStyle: paragraphStyle
        ]
        (text as NSString).draw(in: drawRect, withAttributes: fillAttrs)
        
        NSGraphicsContext.restoreGraphicsState()
        
        if let pngData = rep.representation(using: .png, properties: [:]) {
            do {
                try pngData.write(to: cuePath)
            } catch {
                print("[ERROR] Failed to write subtitle PNG to \(cuePath.path): \(error)")
            }
        }
    }
}

queue.waitUntilAllOperationsAreFinished()
print("All subtitle PNGs rendered successfully!")

// 3. Build ffconcat file covering 0.0s -> totalDur
var sortedCues = cues.compactMap { cue -> (id: Int, start: Double, end: Double)? in
    guard let id = cue["id"] as? Int else { return nil }
    let start = (cue["sub_start"] as? Double) ?? (cue["start"] as? Double) ?? 0.0
    let end = (cue["sub_end"] as? Double) ?? (cue["end"] as? Double) ?? 0.0
    guard end > start else { return nil }
    return (id, start, end)
}
sortedCues.sort { $0.start < $1.start }

var concatLines: [String] = ["ffconcat version 1.0"]
var curTime = 0.0

for cue in sortedCues {
    let s = max(curTime, cue.start)
    let e = min(totalDur, cue.end)
    if s >= totalDur { break }
    
    // Silence / empty frame before cue
    if s > curTime + 0.01 {
        let gap = s - curTime
        concatLines.append("file 'empty.png'")
        concatLines.append(String(format: "duration %.4f", gap))
        curTime = s
    }
    
    if e > curTime + 0.01 {
        let cueDur = e - curTime
        let cueFile = String(format: "cue_%04d.png", cue.id)
        let exists = FileManager.default.fileExists(atPath: outDirUrl.appendingPathComponent(cueFile).path)
        // CRITICAL FIX: If cue has no PNG (e.g. empty/sign cue), safely use empty.png
        concatLines.append("file '\(exists ? cueFile : "empty.png")'")
        concatLines.append(String(format: "duration %.4f", cueDur))
        curTime = e
    }
}

if curTime < totalDur - 0.01 {
    let remaining = totalDur - curTime
    concatLines.append("file 'empty.png'")
    concatLines.append(String(format: "duration %.4f", remaining))
}

// Final hold frame
concatLines.append("file 'empty.png'")

let concatPath = outDirUrl.appendingPathComponent("subs_sample.txt")
let concatContent = concatLines.joined(separator: "\n")
do {
    try concatContent.write(to: concatPath, atomically: true, encoding: .utf8)
    print("Saved ffconcat subtitle playlist to \(concatPath.path)")
} catch {
    print("[ERROR] Failed to save ffconcat subtitle playlist: \(error)")
    exit(1)
}
