import AVFoundation
import Foundation

enum SynthesisError: Error, CustomStringConvertible {
    case invalidArguments
    case missingVoice
    case emptyText
    case failedToCreateOutputFormat
    case failedToCreateOutputBuffer
    case failedToWriteAudio(String)
    case noAudioProduced
    case synthesisTimedOut

    var description: String {
        switch self {
        case .invalidArguments:
            return "Usage: swift 01_tts_apple.swift <input_txt> <output_wav> [voice_id]"
        case .missingVoice:
            return "Unable to resolve an Apple speech voice for the requested identifier or language."
        case .emptyText:
            return "Input narration text is empty."
        case .failedToCreateOutputFormat:
            return "Failed to create the output audio format."
        case .failedToCreateOutputBuffer:
            return "Failed to create the output audio buffer."
        case .failedToWriteAudio(let reason):
            return "Failed to write audio: \(reason)"
        case .noAudioProduced:
            return "Apple AVFoundation speech synthesis produced no audio."
        case .synthesisTimedOut:
            return "Apple AVFoundation speech synthesis timed out before completion."
        }
    }
}

final class BufferWriter {
    private let outputURL: URL
    private var audioFile: AVAudioFile?
    private var converter: AVAudioConverter?
    private var outputFormat: AVAudioFormat?
    private var totalFrames: AVAudioFramePosition = 0

    init(outputURL: URL) {
        self.outputURL = outputURL
    }

    func append(_ pcmBuffer: AVAudioPCMBuffer) throws {
        let format = pcmBuffer.format

        if outputFormat == nil {
            guard let createdFormat = AVAudioFormat(
                commonFormat: .pcmFormatInt16,
                sampleRate: format.sampleRate,
                channels: format.channelCount,
                interleaved: true
            ) else {
                throw SynthesisError.failedToCreateOutputFormat
            }

            outputFormat = createdFormat
            converter = AVAudioConverter(from: format, to: createdFormat)
            audioFile = try AVAudioFile(
                forWriting: outputURL,
                settings: createdFormat.settings,
                commonFormat: createdFormat.commonFormat,
                interleaved: createdFormat.isInterleaved
            )
        }

        guard let converter, let outputFormat, let audioFile else {
            throw SynthesisError.failedToCreateOutputFormat
        }

        let ratio = outputFormat.sampleRate / format.sampleRate
        let frameCapacity = AVAudioFrameCount(Double(pcmBuffer.frameLength) * ratio) + 1024
        guard let convertedBuffer = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: frameCapacity) else {
            throw SynthesisError.failedToCreateOutputBuffer
        }

        var localError: NSError?
        var consumed = false
        let status = converter.convert(to: convertedBuffer, error: &localError) { _, status in
            if consumed {
                status.pointee = .noDataNow
                return nil
            }

            consumed = true
            status.pointee = .haveData
            return pcmBuffer
        }

        if status == .error {
            throw SynthesisError.failedToWriteAudio(localError?.localizedDescription ?? "Audio converter returned .error")
        }

        if convertedBuffer.frameLength > 0 {
            try audioFile.write(from: convertedBuffer)
            totalFrames += AVAudioFramePosition(convertedBuffer.frameLength)
        }
    }

    var wroteAudio: Bool {
        totalFrames > 0
    }
}

func resolveVoice(identifier: String?) -> AVSpeechSynthesisVoice? {
    if let identifier, !identifier.isEmpty {
        if let direct = AVSpeechSynthesisVoice(identifier: identifier) {
            return direct
        }

        if let named = AVSpeechSynthesisVoice.speechVoices().first(where: {
            $0.identifier == identifier || $0.name == identifier
        }) {
            return named
        }
    }

    return AVSpeechSynthesisVoice(language: "zh-CN")
        ?? AVSpeechSynthesisVoice.speechVoices().first(where: { $0.language.hasPrefix("zh") })
}

func main() throws {
    let arguments = CommandLine.arguments
    guard arguments.count >= 3 else {
        throw SynthesisError.invalidArguments
    }

    let inputURL = URL(fileURLWithPath: arguments[1])
    let outputURL = URL(fileURLWithPath: arguments[2])
    let requestedVoice = arguments.count >= 4 ? arguments[3] : ProcessInfo.processInfo.environment["APPLE_TTS_VOICE_ID"]

    let text = try String(contentsOf: inputURL, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)
    if text.isEmpty {
        throw SynthesisError.emptyText
    }

    guard let voice = resolveVoice(identifier: requestedVoice) else {
        throw SynthesisError.missingVoice
    }

    let utterance = AVSpeechUtterance(string: text)
    utterance.voice = voice
    utterance.rate = 0.47
    utterance.pitchMultiplier = 1.0
    utterance.volume = 1.0
    utterance.prefersAssistiveTechnologySettings = false

    let writer = BufferWriter(outputURL: outputURL)
    let synthesizer = AVSpeechSynthesizer()
    var finished = false
    var callbackError: Error?

    synthesizer.write(utterance) { buffer in
        guard let pcmBuffer = buffer as? AVAudioPCMBuffer else {
            finished = true
            return
        }

        if pcmBuffer.frameLength == 0 {
            finished = true
            return
        }

        do {
            try writer.append(pcmBuffer)
        } catch {
            callbackError = error
            finished = true
        }
    }

    let deadline = Date().addingTimeInterval(300)
    while !finished && Date() < deadline {
        RunLoop.current.run(mode: .default, before: Date(timeIntervalSinceNow: 0.1))
    }

    if let callbackError {
        throw callbackError
    }

    if !finished {
        throw SynthesisError.synthesisTimedOut
    }

    if !writer.wroteAudio {
        throw SynthesisError.noAudioProduced
    }

    print("Apple AVFoundation narration generated: \(outputURL.path)")
}

do {
    try main()
} catch {
    fputs("\(error)\n", stderr)
    exit(1)
}
