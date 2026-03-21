// Models/SubtitleEntry.cs
// Model đại diện cho 1 dòng subtitle trong DataGrid
using CommunityToolkit.Mvvm.ComponentModel;

namespace VideoLocalizer.Models;

/// <summary>
/// 1 subtitle entry = 1 dòng trong file SRT
/// Kế thừa ObservableObject để DataGrid tự cập nhật khi text thay đổi
/// </summary>
public partial class SubtitleEntry : ObservableObject
{
    /// <summary>Số thứ tự trong file SRT (1-indexed)</summary>
    [ObservableProperty]
    private int _index;

    /// <summary>Thời điểm bắt đầu hiển thị sub (hh:mm:ss,ms)</summary>
    [ObservableProperty]
    private TimeSpan _startTime;

    /// <summary>Thời điểm kết thúc hiển thị sub</summary>
    [ObservableProperty]
    private TimeSpan _endTime;

    /// <summary>Nội dung text (có thể edit trực tiếp trên DataGrid)</summary>
    [ObservableProperty]
    private string _text = string.Empty;

    /// <summary>
    /// Helper: format StartTime → string "00:01:23,456" để hiển thị trên DataGrid
    /// </summary>
    public string StartTimeDisplay =>
        $"{StartTime.Hours:D2}:{StartTime.Minutes:D2}:{StartTime.Seconds:D2},{StartTime.Milliseconds:D3}";

    /// <summary>
    /// Helper: format EndTime → string "00:01:25,789"
    /// </summary>
    public string EndTimeDisplay =>
        $"{EndTime.Hours:D2}:{EndTime.Minutes:D2}:{EndTime.Seconds:D2},{EndTime.Milliseconds:D3}";
}
