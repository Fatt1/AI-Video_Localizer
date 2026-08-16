using System.Text.Json.Serialization;

namespace VideoLocalizer.Models;

public class VoiceClone
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("ref_audio")]
    public string RefAudio { get; set; } = string.Empty;

    [JsonPropertyName("ref_text")]
    public string RefText { get; set; } = string.Empty;

    [JsonPropertyName("has_transcript")]
    public bool HasTranscript { get; set; }

    [JsonPropertyName("engine")]
    public string Engine { get; set; } = "omnivoice";
}

public class VoicesResponse
{
    [JsonPropertyName("voices")]
    public List<VoiceClone> Voices { get; set; } = new();
}
