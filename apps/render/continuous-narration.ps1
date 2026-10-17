param([string]$InputFile, [string]$WaveFile, [string]$TimingFile)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
Add-Type -ReferencedAssemblies System.Speech -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Speech.Synthesis;
using System.Speech.AudioFormat;
public class AlignedSpeech {
  public static List<string> Marks = new List<string>();
  public static void Render(string ssml, string wave) {
    using (var synth = new SpeechSynthesizer()) {
      synth.SelectVoiceByHints(VoiceGender.Female, VoiceAge.Adult, 0, new System.Globalization.CultureInfo("zh-CN"));
      synth.BookmarkReached += (sender, e) => Marks.Add(e.Bookmark + "|" + e.AudioPosition.TotalMilliseconds.ToString(System.Globalization.CultureInfo.InvariantCulture));
      synth.SetOutputToWaveFile(wave, new SpeechAudioFormatInfo(16000, AudioBitsPerSample.Sixteen, AudioChannel.Mono));
      synth.SpeakSsml(ssml);
    }
  }
}
'@
$parts = Get-Content -LiteralPath $InputFile -Raw -Encoding UTF8 | ConvertFrom-Json
$body = ($parts | ForEach-Object {
  '<mark name="' + $_.id + '"/>' + [System.Security.SecurityElement]::Escape($_.text)
}) -join ''
$ssml = '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="zh-CN"><prosody rate="medium">' + $body + '<mark name="end"/></prosody></speak>'
[AlignedSpeech]::Render($ssml, $WaveFile)
$marks = @([AlignedSpeech]::Marks | ForEach-Object {
  $values = $_.Split('|')
  @{ id=$values[0]; ms=[double]::Parse($values[1], [System.Globalization.CultureInfo]::InvariantCulture) }
})
[IO.File]::WriteAllText($TimingFile, (ConvertTo-Json -InputObject $marks), [Text.UTF8Encoding]::new($false))
