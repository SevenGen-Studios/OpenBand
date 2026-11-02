// Local-only Vision OCR. Language correction is disabled to preserve source names/numbers.
// https://developer.apple.com/documentation/vision/vnrecognizetextrequest
import Foundation
import Vision
import ImageIO
import Darwin
func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8)); exit(1)
}
if CommandLine.arguments.count != 2 { fail("Expected one local image path") }
let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
      let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { fail("Image unavailable") }
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["en-US"]
request.usesLanguageCorrection = false
request.usesCPUOnly = true
let handler = VNImageRequestHandler(cgImage: image, options: [:])
do { try handler.perform([request]) } catch { fail("Vision OCR unavailable: \(error)") }
let cells: [[String:Any]] = (request.results ?? []).compactMap { observation in
    guard let candidate = observation.topCandidates(1).first else { return nil }
    let box = observation.boundingBox
    let x = box.minX * Double(image.width)
    let y = (1 - box.maxY) * Double(image.height)
    let w = box.width * Double(image.width)
    let h = box.height * Double(image.height)
    return ["text":candidate.string, "confidence":candidate.confidence,
            "box":[[x,y],[x+w,y],[x+w,y+h],[x,y+h]]]
}
let data = try JSONSerialization.data(withJSONObject: cells, options: [.sortedKeys])
FileHandle.standardOutput.write(data)
