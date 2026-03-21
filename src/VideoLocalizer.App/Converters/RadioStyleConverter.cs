// Converters/RadioStyleConverter.cs
// Converter đặc biệt cho RadioButton ↔ string binding
// Vì WPF RadioButton không hỗ trợ binding string trực tiếp
using System.Globalization;
using System.Windows.Data;

namespace VideoLocalizer.Converters;

/// <summary>
/// Cho phép bind RadioButton.IsChecked vào 1 string property trong ViewModel.
///
/// Cách dùng trong XAML:
///   IsChecked="{Binding SelectedStyle,
///       Converter={StaticResource RadioStyleConverter},
///       ConverterParameter=lifestyle}"
///
/// Khi SelectedStyle == ConverterParameter → IsChecked = true
/// Khi user check RadioButton → SelectedStyle = ConverterParameter
/// </summary>
public class RadioStyleConverter : IValueConverter
{
    /// <summary>ViewModel → View: nếu value == parameter thì IsChecked = true</summary>
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        return value?.ToString() == parameter?.ToString();
    }

    /// <summary>View → ViewModel: khi RadioButton được check, trả về parameter string</summary>
    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
    {
        // Chỉ cập nhật khi được check (true), bỏ qua khi uncheck (false)
        if (value is bool isChecked && isChecked)
            return parameter?.ToString() ?? string.Empty;

        return Binding.DoNothing;
    }
}
