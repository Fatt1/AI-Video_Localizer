// Services/ApiService.cs
// HTTP client đầy đủ giao tiếp với Python FastAPI backend
// Step 6: POST task → nhận task_id → stream SSE progress → cancel
using System.Net.Http;
using System.Net.Http.Json;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using VideoLocalizer.Models;

namespace VideoLocalizer.Services;

/// <summary>
/// Toàn bộ HTTP communication với Python backend.
/// Singleton — tạo 1 lần trong App, inject vào ViewModel.
/// </summary>
public class ApiService
{
    // HttpClient nên là static/singleton, không tạo mới mỗi lần gọi
    private readonly HttpClient _http;
    private readonly string _baseUrl;

    // JsonSerializer options: snake_case từ Python ↔ PascalCase C#
    private static readonly JsonSerializerOptions _jsonOpts = new()
    {
        PropertyNameCaseInsensitive = true,
        // Python trả về snake_case, C# model dùng [JsonPropertyName] nếu cần
    };

    public ApiService(string baseUrl = "http://localhost:8000")
    {
        _baseUrl = baseUrl.TrimEnd('/');
        _http = new HttpClient
        {
            // SSE stream có thể dài → không set Timeout ở đây
            // Timeout riêng sẽ đặt qua CancellationToken
            Timeout = Timeout.InfiniteTimeSpan
        };
    }

    // =====================================================================
    // HEALTH CHECK
    // =====================================================================

    /// <summary>
    /// GET /api/v1/health — kiểm tra backend có đang chạy không.
    /// Trả về true nếu status = "ok", false nếu lỗi kết nối.
    /// </summary>
    public async Task<bool> CheckHealthAsync()
    {
        try
        {
            // Timeout ngắn 3s cho health check
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(3));
            var resp = await _http.GetAsync($"{_baseUrl}/api/v1/health", cts.Token);
            if (!resp.IsSuccessStatusCode) return false;

            var health = await resp.Content.ReadFromJsonAsync<HealthResponse>(_jsonOpts);
            return health?.Status == "ok";
        }
        catch
        {
            return false; // Backend chưa chạy hoặc lỗi mạng → false, không crash
        }
    }

    // =====================================================================
    // START TASKS (OCR / Translate)
    // =====================================================================

    /// <summary>
    /// POST /api/v1/ocr — bắt đầu OCR pipeline.
    /// Trả về task_id ngay lập tức (HTTP 202), xử lý background.
    /// </summary>
    /// <param name="videoPath">Đường dẫn video trên máy server/local</param>
    /// <param name="cropRegion">[X, Y, W, H] pixel coordinates</param>
    /// <param name="fps">Frame rate để trích xuất (default 2.0)</param>
    public async Task<TaskStartResponse?> StartOcrAsync(
        string videoPath, int[] cropRegion, float fps = 4.0f)
    {
        var payload = new
        {
            video_path  = videoPath,
            crop_region = cropRegion,
            fps         = fps
        };
        return await PostTaskAsync("/api/v1/ocr", payload);
    }

    /// <summary>
    /// POST /api/v1/translate — bắt đầu dịch SRT.
    /// </summary>
    /// <param name="srtPath">Đường dẫn file .srt gốc</param>
    /// <param name="style">"lifestyle" | "review" | "ancient_drama"</param>
    /// <param name="glossary">Từ điển bắt buộc key=Trung, value=Việt</param>
    public async Task<TaskStartResponse?> StartTranslateAsync(
        string srtPath,
        string style = "lifestyle",
        Dictionary<string, string>? glossary = null)
    {
        var payload = new
        {
            srt_path        = srtPath,
            target_language = "vi",
            style           = style,
            glossary        = glossary ?? new Dictionary<string, string>()
        };
        return await PostTaskAsync("/api/v1/translate", payload);
    }

    // =====================================================================
    // SSE STREAMING
    // =====================================================================

    /// <summary>
    /// GET /api/v1/tasks/{taskId}/stream — nhận SSE events realtime.
    ///
    /// Dùng IAsyncEnumerable → caller có thể dùng "await foreach":
    ///   await foreach (var evt in api.StreamTaskAsync(id, ct))
    ///   {
    ///       UpdateProgress(evt.Progress, evt.Message);
    ///   }
    ///
    /// Stream tự kết thúc khi nhận event type = "complete" hoặc "error".
    /// </summary>
    public async IAsyncEnumerable<SseEvent> StreamTaskAsync(
        string taskId,
        [EnumeratorCancellation] CancellationToken ct = default)
    {
        var url = $"{_baseUrl}/api/v1/tasks/{taskId}/stream";

        HttpResponseMessage response;
        try
        {
            // HttpCompletionOption.ResponseHeadersRead: không buffer toàn bộ body
            // → đọc stream từng dòng (quan trọng cho SSE)
            response = await _http.GetAsync(url,
                HttpCompletionOption.ResponseHeadersRead, ct);
            response.EnsureSuccessStatusCode();
        }
        catch (OperationCanceledException)
        {
            yield break; // User cancel → dừng
        }

        using var stream   = await response.Content.ReadAsStreamAsync(ct);
        using var reader   = new System.IO.StreamReader(stream, Encoding.UTF8);

        // SSE format: mỗi event là "data: {json}\n\n"
        // LỖI NGHIÊM TRỌNG TRƯỚC ĐÂY: `!reader.EndOfStream` sẽ read ĐỒNG BỘ (blocking) 
        // để kiểm tra EOF, gây đơ (freeze) WPF UI chờ mạng. Không bao giờ dùng EndOfStream với NetworkStream!
        while (!ct.IsCancellationRequested)
        {
            var line = await reader.ReadLineAsync(ct);
            
            // ReadLineAsync trả về null nếu stream đã thực sự kết thúc
            if (line == null) break;

            // Bỏ qua dòng trống (phân cách giữa events)
            if (string.IsNullOrWhiteSpace(line)) continue;

            // Chỉ xử lý dòng bắt đầu bằng "data: "
            if (!line.StartsWith("data: ")) continue;

            var json = line[6..]; // Cắt prefix "data: "

            SseEvent? evt = null;
            try
            {
                evt = JsonSerializer.Deserialize<SseEvent>(json, _jsonOpts);
            }
            catch
            {
                continue; // JSON parse lỗi → bỏ qua (keepalive hoặc malformed)
            }

            if (evt == null) continue;

            yield return evt;

            // Dừng stream khi task hoàn thành hoặc thất bại
            if (evt.Type is "complete" or "error") yield break;
        }
    }

    // =====================================================================
    // CANCEL TASK
    // =====================================================================

    /// <summary>
    /// POST /api/v1/tasks/{taskId}/cancel — hủy task đang chạy.
    /// </summary>
    public async Task<bool> CancelTaskAsync(string taskId)
    {
        try
        {
            var resp = await _http.PostAsync(
                $"{_baseUrl}/api/v1/tasks/{taskId}/cancel",
                content: null); // POST không có body
            return resp.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }

    // =====================================================================
    // PRIVATE HELPERS
    // =====================================================================

    /// <summary>Helper: POST JSON payload → nhận TaskStartResponse</summary>
    private async Task<TaskStartResponse?> PostTaskAsync(string endpoint, object payload)
    {
        var json    = JsonSerializer.Serialize(payload);
        var content = new StringContent(json, Encoding.UTF8, "application/json");

        var resp = await _http.PostAsync($"{_baseUrl}{endpoint}", content);
        resp.EnsureSuccessStatusCode();

        return await resp.Content.ReadFromJsonAsync<TaskStartResponse>(_jsonOpts);
    }
}
