using System.Collections.ObjectModel;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using VideoLocalizer.Models;

namespace VideoLocalizer.Views;

public partial class FindReplaceSubtitleDialog : Wpf.Ui.Controls.FluentWindow
{
    private readonly ObservableCollection<SubtitleEntry> _subtitles;
    private bool _isReplacing;
    private bool _isSearching;

    public int LastReplacedLineCount { get; private set; }
    public int LastReplacedOccurrenceCount { get; private set; }

    public FindReplaceSubtitleDialog(ObservableCollection<SubtitleEntry> subtitles)
    {
        InitializeComponent();

        _subtitles = subtitles;
        LstMatches.ItemsSource = Array.Empty<SubtitleEntry>();

        Loaded += async (_, _) =>
        {
            TxtFind.Focus();
            await Task.CompletedTask;
        };
    }

    private async void BtnSearch_Click(object sender, RoutedEventArgs e)
    {
        await ExecuteUserSearchAsync();
    }

    private async void TxtFind_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key != Key.Enter)
            return;

        e.Handled = true;
        await ExecuteUserSearchAsync();
    }

    private async Task ExecuteUserSearchAsync()
    {
        if (_isReplacing || _isSearching)
            return;

        try
        {
            await RunSearchAsync();
        }
        catch (Exception ex)
        {
            TxtResultSummary.Text = "Có lỗi khi tìm kiếm.";
            MessageBox.Show(
                $"Không thể tìm kiếm lúc này: {ex.Message}",
                "Tìm và thay thế SRT",
                MessageBoxButton.OK,
                MessageBoxImage.Warning);
        }
    }

    private async Task RunSearchAsync()
    {
        if (_isSearching)
            return;

        var keyword = TxtFind.Text;
        if (string.IsNullOrEmpty(keyword))
        {
            TxtResultSummary.Text = "Nhập từ cần tìm để xem danh sách đoạn SRT khớp.";
            BtnReplaceAll.IsEnabled = false;
            LstMatches.ItemsSource = Array.Empty<SubtitleEntry>();
            return;
        }

        _isSearching = true;
        BtnSearch.IsEnabled = false;
        BtnReplaceAll.IsEnabled = false;
        TxtResultSummary.Text = "Đang tìm...";

        var snapshot = _subtitles
            .Select(entry => new SubtitleSnapshot(entry, entry.Text ?? string.Empty))
            .ToList();

        try
        {
            var matches = await Task.Run(() =>
            {
                var result = new List<SubtitleEntry>();
                foreach (var item in snapshot)
                {
                    if (item.Text.Contains(keyword, StringComparison.CurrentCultureIgnoreCase))
                        result.Add(item.Entry);
                }
                return result;
            });

            LstMatches.ItemsSource = matches;
            TxtResultSummary.Text = $"Tìm thấy {matches.Count} dòng chứa \"{keyword}\".";
            BtnReplaceAll.IsEnabled = matches.Count > 0;
        }
        catch (Exception ex)
        {
            TxtResultSummary.Text = "Có lỗi khi tìm kiếm.";
            MessageBox.Show(
                $"Không thể tìm kiếm lúc này: {ex.Message}",
                "Tìm và thay thế SRT",
                MessageBoxButton.OK,
                MessageBoxImage.Warning);
        }
        finally
        {
            _isSearching = false;
            BtnSearch.IsEnabled = true;
        }
    }

    private async void BtnReplaceAll_Click(object sender, RoutedEventArgs e)
    {
        await ReplaceAllAsync();
    }

    private async Task ReplaceAllAsync()
    {
        try
        {
            var keyword = TxtFind.Text;
            if (string.IsNullOrEmpty(keyword))
            {
                MessageBox.Show(
                "Vui lòng nhập từ cần tìm trước khi thay thế.",
                "Tìm và thay thế SRT",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
                return;
            }

            if (_isReplacing)
                return;

            var replacement = TxtReplace.Text ?? string.Empty;
            var regex = new Regex(Regex.Escape(keyword), RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

            _isReplacing = true;
            BtnSearch.IsEnabled = false;
            BtnReplaceAll.IsEnabled = false;
            TxtResultSummary.Text = "Đang thay thế...";

            var snapshot = _subtitles
                .Select(entry => new SubtitleSnapshot(entry, entry.Text ?? string.Empty))
                .ToList();

            var replaceResults = await Task.Run(() =>
            {
                var results = new List<ReplaceResult>();
                foreach (var item in snapshot)
                {
                    if (item.Text.Length == 0)
                        continue;

                    var matches = regex.Matches(item.Text);
                    if (matches.Count == 0)
                        continue;

                    var updatedText = regex.Replace(item.Text, replacement);
                    results.Add(new ReplaceResult(item.Entry, updatedText, matches.Count));
                }
                return results;
            });

            int replacedLines = 0;
            int replacedOccurrences = 0;

            foreach (var result in replaceResults)
            {
                result.Entry.Text = result.UpdatedText;
                replacedLines++;
                replacedOccurrences += result.MatchCount;
            }

            LastReplacedLineCount = replacedLines;
            LastReplacedOccurrenceCount = replacedOccurrences;

            _isReplacing = false;
            await RunSearchAsync();

            if (replacedLines == 0)
            {
                MessageBox.Show(
                    "Không có dòng nào được thay thế.",
                    "Tìm và thay thế SRT",
                    MessageBoxButton.OK,
                    MessageBoxImage.Information);
                return;
            }

            MessageBox.Show(
                $"Đã thay thế {replacedOccurrences} lần trên {replacedLines} dòng.\n\nDữ liệu chỉ mới thay đổi trên danh sách hiện tại và chưa được lưu file.",
                "Tìm và thay thế SRT",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                $"Không thể thay thế lúc này: {ex.Message}",
                "Tìm và thay thế SRT",
                MessageBoxButton.OK,
                MessageBoxImage.Warning);
            _isReplacing = false;
            await RunSearchAsync();
        }
        finally
        {
            _isReplacing = false;
            BtnSearch.IsEnabled = true;
        }
    }

    private readonly record struct SubtitleSnapshot(SubtitleEntry Entry, string Text);

    private readonly record struct ReplaceResult(SubtitleEntry Entry, string UpdatedText, int MatchCount);

    private void BtnClose_Click(object sender, RoutedEventArgs e)
    {
        Close();
    }
}
