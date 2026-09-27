from fireredvad import FireRedVad, FireRedVadConfig
import glob
import os

def convert_wav_files():
    wav_paths = glob.glob("responses/*.wav")
    os.makedirs("converted", exist_ok=True)
    for wav_path in wav_paths:
        output_wav_path = f"converted/{os.path.basename(wav_path)}"
        command = f"ffmpeg -i {wav_path} -ar 16000 -ac 1 -acodec pcm_s16le -f wav {output_wav_path}"
        print(command)
        #status = os.system(command)

def test():
    vad_config = FireRedVadConfig(
    use_gpu=False,
    smooth_window_size=5,
    speech_threshold=0.4,
    min_speech_frame=20,
    max_speech_frame=2000,
    min_silence_frame=20,
    merge_silence_frame=0,
    extend_speech_frame=0,
    chunk_max_frame=30000)
    vad = FireRedVad.from_pretrained("pretrained_models/FireRedVAD/VAD", vad_config)
    wav_paths = glob.glob("converted/*.wav")
    wav_paths = sorted(wav_paths)
    for wav_path in wav_paths:
        result, probs = vad.detect(wav_path)
        print(wav_path, result['timestamps'][0][0])


if __name__ == "__main__":
    #convert_wav_files()
    test()
