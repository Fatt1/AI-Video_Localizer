// Views/AddSubtitleDialog.xaml.cs
// Code-behind dialog thêm subtitle mới.
// Trả về SubtitleEntry đã điền khi user bấm OK, null khi Cancel.

using System.Windows;
using System.Windows.Input;
using VideoLocalizer.Models;

namespace VideoLocalizer.Views;

public partial class AddSubtitleDialog : Wpf.Ui.Controls.FluentWindow
{
    // ── Kết quả trả về sau khi dialog đóng ──
    public SubtitleEntry? Result { get; private set; }

    // ── Vị trí video hiện tại (ms) — dùng để stamp bằng nút 📍 ──
    private readonly long _currentPositionMs;

    /// <param name="suggestedStartMs">Vị trí video hiện tại (ms), dùng pre-fill StartTime</param>
    public AddSubtitleDialog(long suggestedStartMs)
    {
        InitializeComponent();
        _currentPositionMs = suggestedStartMs;

        // Pre-fill StartTime = vị trí video hiện tại
        var start = TimeSpan.FromMilliseconds(suggestedStartMs);
        TxtStart.Text = FormatTime(start);

        // Pre-fill EndTime = start + 2 giây (mặc định hợp lý)
        var end = start + TimeSpan.FromSeconds(2);
        TxtEnd.Text = FormatTime(end);

        // Focus vào TextBox nội dung ngay sau khi mở
        Loaded += (_, _) => TxtContent.Focus();
    }

    // ── Format TimeSpan → "HH:mm:ss,fff" ──
    private static string FormatTime(TimeSpan ts) =>
        $"{(int)ts.TotalHours:D2}:{ts.Minutes:D2}:{ts.Seconds:D2},{ts.Milliseconds:D3}";

    // ── Parse "HH:mm:ss,fff" → TimeSpan, trả null nếu sai định dạng ──
    private static TimeSpan? ParseTime(string text)
    {
        // Hỗ trợ cả dấu phẩy (SRT) và dấu chấm
        text = text.Trim().Replace(',', '.');
        if (TimeSpan.TryParseExact(text, @"hh\:mm\:ss\.fff", null, out var result))
            return result;
        if (TimeSpan.TryParse(text.Replace('.', ':'), out result))
            return result;
        return null;
    }

    // ── Nút 📍 Stamp StartTime từ vị trí video ──
    private void BtnStampStart_Click(object sender, RoutedEventArgs e)
    {
        TxtStart.Text = FormatTime(TimeSpan.FromMilliseconds(_currentPositionMs));
    }

    // ── Nút 📍 Stamp EndTime từ vị trí video ──
    private void BtnStampEnd_Click(object sender, RoutedEventArgs e)
    {
        TxtEnd.Text = FormatTime(TimeSpan.FromMilliseconds(_currentPositionMs));
    }

    // ── Ctrl+Enter trong TextBox nội dung → OK ──
    private void TxtContent_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Return && Keyboard.Modifiers == ModifierKeys.Control)
            BtnOk_Click(sender, e);
    }

    private void BtnOk_Click(object sender, RoutedEventArgs e)
    {
        var start = ParseTime(TxtStart.Text);
        var end   = ParseTime(TxtEnd.Text);

        if (start == null)
        {
            MessageBox.Show("Định dạng thời gian bắt đầu không hợp lệ.\nVí dụ: 00:01:23,456",
                            "Lỗi", MessageBoxButton.OK, MessageBoxImage.Warning);
            TxtStart.Focus();
            return;
        }

        if (end == null)
        {
            MessageBox.Show("Định dạng thời gian kết thúc không hợp lệ.\nVí dụ: 00:01:25,789",
                            "Lỗi", MessageBoxButton.OK, MessageBoxImage.Warning);
            TxtEnd.Focus();
            return;
        }

        if (end <= start)
        {
            MessageBox.Show("Thời gian kết thúc phải lớn hơn thời gian bắt đầu.",
                            "Lỗi", MessageBoxButton.OK, MessageBoxImage.Warning);
            TxtEnd.Focus();
            return;
        }

        Result = new SubtitleEntry
        {
            StartTime = start.Value,
            EndTime   = end.Value,
            Text      = TxtContent.Text.Trim()
        };

        DialogResult = true;
        Close();
    }

    private void BtnCancel_Click(object sender, RoutedEventArgs e)
    {
        Result = null;
        DialogResult = false;
        Close();
    }
}
