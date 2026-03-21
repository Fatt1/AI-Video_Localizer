// Converters/TimeSpanConverter.cs
// Chuyển đổi TimeSpan ↔ string "hh:mm:ss,ms" để dùng trong XAML binding
using System.Globalization;
using System.Windows.Data;

namespace VideoLocalizer.Converters;

/// <summary>
/// IValueConverter: TimeSpan → string "00:01:23,456"
/// Dùng trong DataGrid để hiển thị Start/End time
/// </summary>
public class TimeSpanConverter : IValueConverter
{
    /// <summary>
    /// Convert TimeSpan → string dạng SRT time
    /// VD: TimeSpan(0,1,23,456ms) → "00:01:23,456"
    /// </summary>
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        if (value is TimeSpan ts)
            return $"{ts.Hours:D2}:{ts.Minutes:D2}:{ts.Seconds:D2},{ts.Milliseconds:D3}";
        return string.Empty;
    }

    /// <summary>
    /// ConvertBack: string "00:01:23,456" → TimeSpan
    /// Dùng khi user edit cell trên DataGrid
    /// </summary>
    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
    {
        if (value is string s && TimeSpan.TryParseExact(
            s.Replace(',', '.'),
            @"hh\:mm\:ss\.fff",
            culture,
            out TimeSpan result))
        {
            return result;
        }
        // Trả về giá trị không thay đổi nếu parse thất bại
        return Binding.DoNothing;
    }
}
