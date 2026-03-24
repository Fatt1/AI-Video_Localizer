// Models/ApiResponse.cs
// DTO deserialize JSON từ Python backend (snake_case) → C# (PascalCase)
// QUAN TRỌNG: phải có [JsonPropertyName] cho mọi field snake_case
// vì JsonSerializerOptions.PropertyNameCaseInsensitive không đủ cho snake_case
using System.Text.Json.Serialization;

namespace VideoLocalizer.Models;

/// <summary>
/// Response khi POST /api/v1/ocr hoặc /api/v1/translate
/// Python trả: { "task_id": "...", "stream_url": "..." }
/// </summary>
public class TaskStartResponse
{
    // "task_id" (Python) → TaskId (C#)
    [JsonPropertyName("task_id")]
    public string TaskId { get; set; } = string.Empty;

    [JsonPropertyName("message")]
    public string Message { get; set; } = string.Empty;

    [JsonPropertyName("stream_url")]
    public string StreamUrl { get; set; } = string.Empty;
}

/// <summary>
/// SSE event nhận được từ stream /api/v1/tasks/{id}/stream
/// type = "progress" | "complete" | "error" | "keepalive"
/// Python gửi: { "type": "...", "task_id": "...", "progress": 50, ... }
/// </summary>
public class SseEvent
{
    [JsonPropertyName("type")]
    public string Type { get; set; } = string.Empty;

    [JsonPropertyName("task_id")]
    public string TaskId { get; set; } = string.Empty;

    [JsonPropertyName("progress")]
    public int Progress { get; set; }

    [JsonPropertyName("message")]
    public string Message { get; set; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;

    [JsonPropertyName("result")]
    public SseResult? Result { get; set; }
}

/// <summary>Phần result khi type = "complete"</summary>
public class SseResult
{
    [JsonPropertyName("srt_path")]
    public string SrtPath { get; set; } = string.Empty;

    [JsonPropertyName("subtitle_count")]
    public int SubtitleCount { get; set; }

    [JsonPropertyName("total_lines")]
    public int TotalLines { get; set; }
}

/// <summary>Response GET /api/v1/health</summary>
public class HealthResponse
{
    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;

    [JsonPropertyName("message")]
    public string Message { get; set; } = string.Empty;
}

/// <summary>Response GET /api/v1/tasks/{taskId}/status</summary>
public class TaskStatusResponse
{
    [JsonPropertyName("task_id")]
    public string TaskId { get; set; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;

    [JsonPropertyName("progress")]
    public int Progress { get; set; }

    [JsonPropertyName("message")]
    public string Message { get; set; } = string.Empty;

    [JsonPropertyName("result")]
    public SseResult? Result { get; set; }

    [JsonPropertyName("error")]
    public string? Error { get; set; }
}
