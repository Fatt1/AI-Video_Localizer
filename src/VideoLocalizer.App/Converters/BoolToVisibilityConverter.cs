// Converters/BoolToVisibilityConverter.cs
// Chuyển bool → Visibility để ẩn/hiện UI elements trong XAML
using System.Globalization;
using System.Windows;
using System.Windows.Data;

namespace VideoLocalizer.Converters;

/// <summary>
/// IValueConverter: bool → Visibility
/// true  → Visible
/// false → Collapsed (mặc định) hoặc Hidden (nếu parameter = "Hidden")
///
/// Dùng để ẩn/hiện progress bar, overlay khi đang xử lý, v.v.
/// </summary>
public class BoolToVisibilityConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        bool isVisible = value is bool b && b;

        // Hỗ trợ đảo ngược: parameter = "Invert" → true thì ẩn, false thì hiện
        if (parameter is string p && p == "Invert")
            isVisible = !isVisible;

        return isVisible ? Visibility.Visible : Visibility.Collapsed;
    }

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
    {
        return value is Visibility v && v == Visibility.Visible;
    }
}
