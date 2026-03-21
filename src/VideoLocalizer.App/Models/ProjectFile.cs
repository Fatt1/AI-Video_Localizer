// Models/ProjectFile.cs
// Model lưu trạng thái toàn bộ 1 project (.avlproj)
namespace VideoLocalizer.Models;

/// <summary>
/// Toàn bộ thông tin của 1 project được serialize thành JSON (.avlproj)
/// </summary>
public class ProjectFile
{
    /// <summary>Version format file để backward compatibility</summary>
    public string Version { get; set; } = "1.0";

    /// <summary>Đường dẫn file video (local path)</summary>
    public string VideoPath { get; set; } = string.Empty;

    /// <summary>Danh sách SRT files liên quan (original, ocr, translated...)</summary>
    public List<string> SrtFiles { get; set; } = new();

    /// <summary>Style dịch đang chọn: "review" | "ancient_drama" | "lifestyle"</summary>
    public string TranslationStyle { get; set; } = "lifestyle";

    /// <summary>
    /// Từ điển bắt buộc (Glossary): key = tiếng Trung, value = tiếng Việt
    /// VD: { "大师姐": "Đại sư tỷ" }
    /// </summary>
    public Dictionary<string, string> Glossary { get; set; } = new();

    /// <summary>Vị trí video lần cuối xem (seconds) để resume</summary>
    public double LastPosition { get; set; } = 0;

    /// <summary>URL backend Python (override từ Settings)</summary>
    public string BackendUrl { get; set; } = "http://localhost:8000";

    /// <summary>Thời điểm tạo project</summary>
    public DateTime CreatedAt { get; set; } = DateTime.Now;

    /// <summary>Thời điểm lưu gần nhất</summary>
    public DateTime UpdatedAt { get; set; } = DateTime.Now;
}
