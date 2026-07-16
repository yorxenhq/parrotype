# Generate synthetic test WAVs via Windows SAPI (System.Speech).
# Output: assets/latency_test.wav (EN, ~10s) and test_ru.wav / test_en.wav in tests/data.
# Run: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/make_test_audio.ps1

Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer

Write-Host "Installed voices:"
$voices = $synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo }
$voices | ForEach-Object { Write-Host ("  " + $_.Name + " | " + $_.Culture) }

$root = Split-Path -Parent $PSScriptRoot
$dataDir = Join-Path $root "tests\data"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)

function Speak-ToWav($voice, $text, $path, $rate) {
    $synth.SelectVoice($voice)
    $synth.Rate = $rate
    $synth.SetOutputToWaveFile($path, $fmt)
    $synth.Speak($text)
    $synth.SetOutputToNull()
    Write-Host "Wrote $path"
}

# English phrase (always present on Win11)
$enVoice = ($voices | Where-Object { $_.Culture.Name -like "en-*" } | Select-Object -First 1).Name
$enText = "Open the settings window and check the latency table. The quick brown fox jumps over the lazy dog. Parrot type converts speech to text on this machine, fully offline, using the whisper model."
if ($enVoice) {
    Speak-ToWav $enVoice $enText (Join-Path $dataDir "test_en.wav") 0
    Speak-ToWav $enVoice $enText (Join-Path $root "assets\latency_test.wav") 0
} else {
    Write-Host "NO ENGLISH VOICE FOUND"
}

# Russian phrase with English tech terms (the main acceptance case)
$ruVoice = ($voices | Where-Object { $_.Culture.Name -like "ru-*" } | Select-Object -First 1).Name
$ruText = "Привет, собери отчёт по проекту и отправь его в телеграм. Открой в с код и запусти сервер. Модель работает локально, аудио никуда не отправляется."
if ($ruVoice) {
    Speak-ToWav $ruVoice $ruText (Join-Path $dataDir "test_ru.wav") 0
} else {
    Write-Host "NO RUSSIAN VOICE FOUND"
}
