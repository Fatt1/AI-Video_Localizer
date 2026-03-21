// Services/SubtitleService.cs — Stub: đọc/ghi file SRT
// Sẽ implement đầy đủ ở Step 8-9
using System.IO;
using System.Text.RegularExpressions;
using VideoLocalizer.Models;

namespace VideoLocalizer.Services;

/// <summary>
/// Parse file SRT → List, Save List → file SRT
/// </summary>
public static class SubtitleService
{
    /// <summary>
    /// Đọc file .srt → danh sách SubtitleEntry
    /// Format SRT chuẩn:
    ///   1
    ///   00:00:01,000 --> 00:00:03,500
    ///   Nội dung dòng sub
    /// </summary>
    public static List<SubtitleEntry> Parse(string srtPath)
    {
        var result = new List<SubtitleEntry>();
        var content = File.ReadAllText(srtPath, System.Text.Encoding.UTF8);

        // Tách từng block bằng dòng trống
        var blocks = content.Split(new[] { "\r\n\r\n", "\n\n" },
            StringSplitOptions.RemoveEmptyEntries);

        foreach (var block in blocks)
        {
            var lines = block.Trim().Split(new[] { "\r\n", "\n" },
                StringSplitOptions.None);

            if (lines.Length < 2) continue;

            // Dòng 1: index
            if (!int.TryParse(lines[0].Trim(), out int index)) continue;

            // Dòng 2: timestamp "00:00:01,000 --> 00:00:03,500"
            var timeParts = lines[1].Split(new[] { " --> " }, StringSplitOptions.None);
            if (timeParts.Length != 2) continue;

            if (!TryParseTime(timeParts[0].Trim(), out TimeSpan start)) continue;
            if (!TryParseTime(timeParts[1].Trim(), out TimeSpan end)) continue;

            // Dòng 3+: text (có thể nhiều dòng)
            var text = string.Join("\n", lines.Skip(2));

            result.Add(new SubtitleEntry
            {
                Index = index,
                StartTime = start,
                EndTime = end,
                Text = text
            });
        }

        return result;
    }

    /// <summary>
    /// Lưu danh sách SubtitleEntry → file .srt
    /// </summary>
    public static void Save(IEnumerable<SubtitleEntry> entries, string srtPath)
    {
        using var writer = new StreamWriter(srtPath, false, System.Text.Encoding.UTF8);
        foreach (var entry in entries)
        {
            writer.WriteLine(entry.Index);
            writer.WriteLine($"{FormatTime(entry.StartTime)} --> {FormatTime(entry.EndTime)}");
            writer.WriteLine(entry.Text);
            writer.WriteLine(); // Dòng trống phân cách
        }
    }

    // ── Helpers ──

    private static bool TryParseTime(string s, out TimeSpan result)
    {
        // Format: "hh:mm:ss,fff" (dấu phẩy, không phải dấu chấm)
        return TimeSpan.TryParseExact(s.Replace(',', '.'),
            @"hh\:mm\:ss\.fff",
            null,
            out result);
    }

    private static string FormatTime(TimeSpan ts) =>
        $"{ts.Hours:D2}:{ts.Minutes:D2}:{ts.Seconds:D2},{ts.Milliseconds:D3}";
}
