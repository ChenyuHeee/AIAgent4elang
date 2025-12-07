import Foundation

// Placeholder Swift Vision CLI. Replace with real Vision-based OCR when ready.
let args = CommandLine.arguments
if args.count < 2 {
    print("{\"text\":\"\",\"error\":\"no image path provided\"}")
    exit(1)
}
let imagePath = args[1]
let payload: [String: String] = [
    "text": "",
    "error": "Vision OCR not implemented yet",
    "image": imagePath
]
if let data = try? JSONSerialization.data(withJSONObject: payload, options: []) {
    print(String(data: data, encoding: .utf8)!)
} else {
    print("{\"text\":\"\",\"error\":\"failed to encode JSON\"}")
    exit(1)
}
