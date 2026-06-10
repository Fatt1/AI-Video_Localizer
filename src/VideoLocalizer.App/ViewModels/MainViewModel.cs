// ViewModels/MainViewModel.cs
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Microsoft.Win32;
using System.Collections.Specialized;
using System.Collections.ObjectModel;
using System.Text;
using System.Threading;
using System.Windows;
using VideoLocalizer.Models;
using VideoLocalizer.Services;

namespace VideoLocalizer.ViewModels;

/// <summary>
/// MainViewModel: toàn bộ logic binding cho MainWindow
/// Kế thừa ObservableObject → tự INotifyPropertyChanged
/// </summary>
public partial class MainViewModel : ObservableObject
{
    private static readonly TimeSpan MinExpectedSubtitleDuration = TimeSpan.FromSeconds(1);

    // =====================================================================
    // SERVICES
    // =====================================================================

    /// <summary>
    /// ApiService: gọi HTTP đến Python backend.
    /// Khởi tạo với URL mặc định, có thể override từ Settings.
    /// </summary>
    public ApiService Api { get; } = new ApiService("http://localhost:8000");

    // =====================================================================
    // TASK TRACKING
    // =====================================================================

    /// <summary>ID của task đang chạy (OCR hoặc Translate)</summary>
    private string? _currentTaskId;

    /// <summary>Dùng để cancel task đang chạy khi user bấm "Hủy"</summary>
    private CancellationTokenSource? _cancelSource;

    // =====================================================================
    // VIDEO PLAYER STATE
    // =====================================================================

    /// <summary>Đường dẫn video hiện tại đang load</summary>
    [ObservableProperty]
    private string _videoPath = string.Empty;

    /// <summary>Vị trí hiện tại của video (milliseconds) — dùng để highlight sub</summary>
    [ObservableProperty]
    private long _currentPositionMs = 0;

    /// <summary>
    /// Vùng chọn OCR hiện tại (tỉ lệ 0–1).
    /// Set từ code-behind sau khi user kéo chuột trên Canvas.
    /// </summary>
    public OcrRegion OcrRegion { get; set; } = OcrRegion.Default;

    /// <summary>
    /// Kích thước VideoView control (pixel) để convert OcrRegion → pixel coords.
    /// Set từ code-behind khi VideoView SizeChanged.
    /// </summary>
    public System.Windows.Size VideoViewSize { get; set; }

    /// <summary>
    /// Kích thước nguồn video gốc (pixel). Ưu tiên dùng để convert crop gửi backend.
    /// </summary>
    public System.Windows.Size VideoSourceSize { get; set; }

    // =====================================================================
    // SUBTITLE DATA
    // =====================================================================

    /// <summary>
    /// Danh sách subtitle entries bind vào DataGrid
    /// ObservableCollection tự notify UI khi thêm/xóa item
    /// </summary>
    public ObservableCollection<SubtitleEntry> Subtitles { get; } = new();

    /// <summary>
    /// Danh sách các dòng có khả năng lỗi: thời lượng (End - Start) < 1 giây.
    /// Dùng để hiển thị cảnh báo phía trên bảng subtitle chính.
    /// </summary>
    public ObservableCollection<SubtitleEntry> SuspectedShortDurationSubtitles { get; } = new();

    /// <summary>Thông báo cảnh báo tổng hợp cho danh sách dòng nghi lỗi.</summary>
    [ObservableProperty]
    private string _shortDurationWarningMessage = "Không phát hiện dòng SRT nghi lỗi thời lượng.";

    /// <summary>Dòng sub đang được chọn/highlighted trên DataGrid</summary>
    [ObservableProperty]
    private SubtitleEntry? _selectedSubtitle;

    /// <summary>Đường dẫn file SRT hiện tại (để save)</summary>
    [ObservableProperty]
    private string _currentSrtPath = string.Empty;

    /// <summary>Đường dẫn file SRT so sánh</summary>
    [ObservableProperty]
    private string _compareSrtPath = string.Empty;

    /// <summary>Danh sách subtitle so sánh</summary>
    public ObservableCollection<SubtitleEntry> CompareSubtitles { get; } = new();

    // =====================================================================
    // TRANSLATION SETTINGS (Right panel)
    // =====================================================================

    /// <summary>
    /// Style dịch đang chọn (bind với RadioButton group)
    /// Giá trị: "lifestyle" | "review" | "ancient_drama"
    /// </summary>
    [ObservableProperty]
    private string _selectedStyle = "lifestyle";

    /// <summary>
    /// Nội dung textbox Từ điển bắt buộc (Glossary)
    /// Format mỗi dòng: "大师姐 = Đại sư tỷ"
    /// </summary>
    [ObservableProperty]
    private string _glossaryText = string.Empty;

    // =====================================================================
    // DUBBING SETTINGS (OmniVoice -> CapCut)
    // =====================================================================

    /// <summary>Danh sách voice clone lấy từ backend.</summary>
    public ObservableCollection<VoiceClone> VoiceClones { get; } = new();

    /// <summary>Voice clone đang chọn cho TTS.</summary>
    [ObservableProperty]
    private VoiceClone? _selectedVoice;

    /// <summary>Tên project CapCut để tìm đúng draft folder.</summary>
    [ObservableProperty]
    private string _capcutProjectName = string.Empty;

    /// <summary>Tốc độ đọc TTS (0.5x -> 2.0x).</summary>
    [ObservableProperty]
    private double _speechRate = 1.0;

    // =====================================================================
    // STT SETTINGS (Fun-ASR-Nano)
    // =====================================================================

    /// <summary>
    /// Số ký tự tối đa trên 1 dòng SRT khi dùng STT (35–42 thông dụng).
    /// Chỉ là trần, không phải mục tiêu — dòng có thể ngắn hơn nếu gặp khoảng lặng.
    /// </summary>
    [ObservableProperty]
    private int _sttMaxCharsPerLine = 42;

    /// <summary>
    /// Khoảng lặng tối thiểu (giây) giữa 2 token để ngắt dòng SRT mới.
    /// Nếu khoảng lặng >= giá trị này thì ngắt dòng dù dòng có ít ký tự.
    /// </summary>
    [ObservableProperty]
    private double _sttSilenceGapS = 1.5;

    // =====================================================================
    // PROGRESS / STATUS
    // =====================================================================

    /// <summary>Text hiển thị trên status bar bên dưới</summary>
    [ObservableProperty]
    private string _statusMessage = "Sẵn sàng";

    /// <summary>Tiến độ task 0–100 (bind vào ProgressBar)</summary>
    [ObservableProperty]
    private int _taskProgress = 0;

    /// <summary>true khi đang chạy OCR/Translate → hiện ProgressBar, ẩn nút</summary>
    [ObservableProperty]
    private bool _isBusy = false;

    /// <summary>true khi đã kết nối được Python backend</summary>
    [ObservableProperty]
    private bool _isBackendConnected = false;

    public MainViewModel()
    {
        Subtitles.CollectionChanged += OnSubtitlesCollectionChanged;
        RefreshSuspectedShortDurationSubtitles();
    }

    // =====================================================================
    // COMMANDS — [RelayCommand] tự tạo ICommand property
    // =====================================================================

    /// <summary>Mở file video từ local disk rồi set VideoPath để code-behind load LibVLC</summary>
    [RelayCommand]
    private void OpenVideo()
    {
        var dialog = new OpenFileDialog
        {
            Title = "Chọn file video",
            // Filter: tên hiển thị | extension patterns
            Filter = "Video files|*.mp4;*.mkv;*.avi;*.mov;*.wmv;*.flv;*.webm|All files|*.*",
            CheckFileExists = true
        };

        // ShowDialog() trả về true khi user chọn file và bấm OK
        if (dialog.ShowDialog() == true)
        {
            VideoPath = dialog.FileName;   // code-behind sẽ watch property này
            StatusMessage = $"Đã mở: {System.IO.Path.GetFileName(dialog.FileName)}";
        }
    }

    /// <summary>Load file SRT vào DataGrid</summary>
    [RelayCommand]
    private void LoadSrt()
    {
        var dialog = new OpenFileDialog
        {
            Title = "Chọn file SRT",
            Filter = "SRT Subtitle files|*.srt|All files|*.*",
            CheckFileExists = true
        };

        if (dialog.ShowDialog() != true) return;

        try
        {
            CurrentSrtPath = dialog.FileName;
            // Parse file SRT → list entries
            var entries = SubtitleService.Parse(dialog.FileName);

            // Xóa danh sách cũ rồi thêm vào
            Subtitles.Clear();
            foreach (var entry in entries)
                Subtitles.Add(entry);

            StatusMessage = $"Đã load {entries.Count} dòng từ {System.IO.Path.GetFileName(dialog.FileName)}";
        }
        catch (Exception ex)
        {
            StatusMessage = $"Lỗi load SRT: {ex.Message}";
        }
    }

    /// <summary>Load file SRT so sánh</summary>
    [RelayCommand]
    private void LoadCompareSrt()
    {
        var dialog = new OpenFileDialog
        {
            Title = "Chọn file SRT việt sub để so sánh",
            Filter = "SRT Subtitle files|*.srt|All files|*.*",
            CheckFileExists = true
        };

        if (dialog.ShowDialog() != true) return;

        try
        {
            CompareSrtPath = dialog.FileName;
            var entries = SubtitleService.Parse(dialog.FileName);
            CompareSubtitles.Clear();
            foreach (var entry in entries) CompareSubtitles.Add(entry);
            StatusMessage = $"Đã load file so sánh: {System.IO.Path.GetFileName(dialog.FileName)} ({entries.Count} dòng)";
        }
        catch (Exception ex)
        {
            StatusMessage = $"Lỗi load SRT so sánh: {ex.Message}";
        }
    }

    /// <summary>Save SRT hiện tại — nếu chưa có path thì mở SaveFileDialog</summary>
    [RelayCommand]
    private void SaveSrt()
    {
        if (Subtitles.Count == 0)
        {
            StatusMessage = "Không có subtitle để lưu.";
            return;
        }

        // Nếu chưa có đường dẫn → hỏi user muốn lưu ở đâu
        if (string.IsNullOrEmpty(CurrentSrtPath))
        {
            var dialog = new SaveFileDialog
            {
                Title = "Lưu file SRT",
                Filter = "SRT Subtitle files|*.srt",
                FileName = "translated.srt"
            };
            if (dialog.ShowDialog() != true) return;
            CurrentSrtPath = dialog.FileName;
        }

        try
        {
            SubtitleService.Save(Subtitles, CurrentSrtPath);
            StatusMessage = $"Đã lưu: {System.IO.Path.GetFileName(CurrentSrtPath)}";
        }
        catch (Exception ex)
        {
            StatusMessage = $"Lỗi lưu SRT: {ex.Message}";
        }
    }

    /// <summary>
    /// Lọc các cụm subtitle bị lặp liên tiếp:
    /// - So sánh text theo tiêu chí giống 100% sau khi Trim 2 đầu.
    /// - Giữ 1 dòng duy nhất với StartTime của dòng đầu và EndTime của dòng cuối cụm.
    /// - Không tự lưu file; user phải bấm Lưu SRT thủ công.
    /// </summary>
    [RelayCommand]
    private void FilterDuplicateSubtitles()
    {
        if (Subtitles.Count < 2)
        {
            StatusMessage = "Không đủ dữ liệu để lọc dòng lặp.";
            return;
        }

        var source = Subtitles.ToList();
        var filtered = new List<SubtitleEntry>(source.Count);
        var detailLines = new List<string>();
        int removedLines = 0;

        int i = 0;
        while (i < source.Count)
        {
            var first = source[i];
            int end = i;

            while (end + 1 < source.Count && AreConsecutiveDuplicates(first, source[end + 1]))
                end++;

            if (end > i)
            {
                var merged = new SubtitleEntry
                {
                    StartTime = first.StartTime,
                    EndTime = source[end].EndTime,
                    Text = first.Text
                };
                filtered.Add(merged);

                removedLines += end - i;

                int firstLineNo = source[i].Index > 0 ? source[i].Index : i + 1;
                int lastLineNo = source[end].Index > 0 ? source[end].Index : end + 1;

                var deletedLineNos = Enumerable.Range(i + 1, end - i)
                    .Select(pos => source[pos].Index > 0 ? source[pos].Index : pos + 1)
                    .ToList();

                var sampleText = (first.Text ?? string.Empty).Trim();
                if (string.IsNullOrEmpty(sampleText))
                    sampleText = "(trống)";
                if (sampleText.Length > 80)
                    sampleText = sampleText[..77] + "...";

                detailLines.Add(
                    $"- Dòng {firstLineNo}-{lastLineNo}: giữ dòng {firstLineNo}, xóa [{string.Join(", ", deletedLineNos)}], nội dung: \"{sampleText}\"");
            }
            else
            {
                filtered.Add(first);
            }

            i = end + 1;
        }

        if (removedLines == 0)
        {
            StatusMessage = "Không có cụm dòng lặp liên tiếp để lọc.";
            MessageBox.Show(
                "Không phát hiện dòng lặp liên tiếp theo tiêu chí: text giống 100% sau khi bỏ khoảng trắng 2 đầu.",
                "Lọc lặp SRT",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
            return;
        }

        Subtitles.Clear();
        foreach (var entry in filtered)
            Subtitles.Add(entry);

        ReIndexSubtitles();
        SelectedSubtitle = Subtitles.FirstOrDefault();

        StatusMessage = $"Đã lọc {detailLines.Count} cụm lặp, xóa {removedLines} dòng. Nhớ bấm 'Lưu SRT' để ghi file.";

        var report = new StringBuilder();
        report.AppendLine("Đã lọc dòng lặp SRT thành công.");
        report.AppendLine($"- Số cụm đã gộp: {detailLines.Count}");
        report.AppendLine($"- Số dòng đã xóa: {removedLines}");
        report.AppendLine("- Lưu ý: Chưa tự lưu file, hãy bấm 'Lưu SRT' khi muốn ghi ra đĩa.");
        report.AppendLine();
        report.AppendLine("Chi tiết từng cụm:");
        foreach (var line in detailLines)
            report.AppendLine(line);

        MessageBox.Show(
            report.ToString(),
            "Kết quả lọc lặp SRT",
            MessageBoxButton.OK,
            MessageBoxImage.Information);
    }

    /// <summary>So sánh SRT gốc với SRT so sánh</summary>
    [RelayCommand]
    private void CompareSrt()
    {
        if (Subtitles.Count == 0)
        {
            MessageBox.Show("Vui lòng load SRT gốc trước.", "So sánh SRT", MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }
        if (CompareSubtitles.Count == 0)
        {
            MessageBox.Show("Vui lòng load SRT việt sub để so sánh trước.", "So sánh SRT", MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }

        var report = new StringBuilder();
        int errorCount = 0;

        int maxLines = Math.Max(Subtitles.Count, CompareSubtitles.Count);
        
        for (int i = 0; i < maxLines; i++)
        {
            var orig = i < Subtitles.Count ? Subtitles[i] : null;
            var comp = i < CompareSubtitles.Count ? CompareSubtitles[i] : null;

            if (orig != null && comp != null)
            {
                if (orig.StartTime != comp.StartTime || orig.EndTime != comp.EndTime)
                {
                    errorCount++;
                    report.AppendLine($"Dòng {i + 1}: Lệch thời gian.");
                    report.AppendLine($"  - Gốc : {orig.StartTime:hh\\:mm\\:ss\\,fff} --> {orig.EndTime:hh\\:mm\\:ss\\,fff}");
                    report.AppendLine($"  - Dịch: {comp.StartTime:hh\\:mm\\:ss\\,fff} --> {comp.EndTime:hh\\:mm\\:ss\\,fff}");
                    report.AppendLine();
                }
            }
            else if (orig == null)
            {
                errorCount++;
                report.AppendLine($"Dòng {i + 1}: Dư ở file dịch (Không có trong gốc).");
                report.AppendLine();
            }
            else if (comp == null)
            {
                errorCount++;
                report.AppendLine($"Dòng {i + 1}: Thiếu ở file dịch (Có trong gốc).");
                report.AppendLine();
            }
        }

        if (errorCount == 0)
        {
            MessageBox.Show("Hai file SRT khớp nhau hoàn toàn về thời gian!", "Kết quả so sánh", MessageBoxButton.OK, MessageBoxImage.Information);
        }
        else
        {
            var scrollViewer = new System.Windows.Controls.ScrollViewer
            {
                VerticalScrollBarVisibility = System.Windows.Controls.ScrollBarVisibility.Auto,
                Margin = new Thickness(10)
            };
            var textBlock = new System.Windows.Controls.TextBlock
            {
                Text = $"Phát hiện {errorCount} lỗi lệch thời gian hoặc số lượng dòng.\n\nChi tiết:\n" + report.ToString(),
                TextWrapping = System.Windows.TextWrapping.Wrap,
                FontFamily = new System.Windows.Media.FontFamily("Consolas")
            };
            scrollViewer.Content = textBlock;

            var window = new Window
            {
                Title = "Kết quả so sánh SRT",
                Content = scrollViewer,
                Width = 600,
                Height = 500,
                WindowStartupLocation = WindowStartupLocation.CenterScreen
            };
            window.ShowDialog();
        }
    }

    private static bool AreConsecutiveDuplicates(SubtitleEntry left, SubtitleEntry right)
    {
        var leftText = (left.Text ?? string.Empty).Trim();
        var rightText = (right.Text ?? string.Empty).Trim();
        return string.Equals(leftText, rightText, StringComparison.Ordinal);
    }

    private void OnSubtitlesCollectionChanged(object? sender, NotifyCollectionChangedEventArgs e)
    {
        if (e.OldItems != null)
        {
            foreach (SubtitleEntry item in e.OldItems)
                item.PropertyChanged -= OnSubtitleEntryPropertyChanged;
        }

        if (e.NewItems != null)
        {
            foreach (SubtitleEntry item in e.NewItems)
                item.PropertyChanged += OnSubtitleEntryPropertyChanged;
        }

        RefreshSuspectedShortDurationSubtitles();
    }

    private void OnSubtitleEntryPropertyChanged(object? sender, System.ComponentModel.PropertyChangedEventArgs e)
    {
        if (e.PropertyName is nameof(SubtitleEntry.StartTime) or nameof(SubtitleEntry.EndTime))
            RefreshSuspectedShortDurationSubtitles();
    }

    private void RefreshSuspectedShortDurationSubtitles()
    {
        var suspects = Subtitles
            .Where(s => (s.EndTime - s.StartTime) < MinExpectedSubtitleDuration)
            .OrderBy(s => s.Index)
            .ToList();

        SuspectedShortDurationSubtitles.Clear();
        foreach (var item in suspects)
            SuspectedShortDurationSubtitles.Add(item);

        ShortDurationWarningMessage = suspects.Count > 0
            ? $"Canh bao: {suspects.Count} dong co thoi luong duoi 1 giay (co kha nang bi loi)."
            : "Khong phat hien dong SRT nghi loi thoi luong (< 1 giay).";
    }

    // =====================================================================
    // SUBTITLE EDITING COMMANDS
    // =====================================================================

    /// <summary>
    /// Chèn subtitle mới TRƯỚC entry chỉ định.
    /// </summary>
    public void AddSubtitleBefore(SubtitleEntry target, SubtitleEntry newEntry)
    {
        int idx = Subtitles.IndexOf(target);
        if (idx < 0) idx = 0;
        Subtitles.Insert(idx, newEntry);
        ReIndexSubtitles();
        SelectedSubtitle = newEntry;
        StatusMessage = $"Đã thêm subtitle trước dòng {idx + 1}";
    }

    /// <summary>
    /// Chèn subtitle mới SAU entry chỉ định.
    /// </summary>
    public void AddSubtitleAfter(SubtitleEntry target, SubtitleEntry newEntry)
    {
        int idx = Subtitles.IndexOf(target);
        int insertAt = (idx >= 0) ? idx + 1 : Subtitles.Count;
        Subtitles.Insert(insertAt, newEntry);
        ReIndexSubtitles();
        SelectedSubtitle = newEntry;
        StatusMessage = $"Đã thêm subtitle sau dòng {idx + 1}";
    }

    /// <summary>
    /// Xóa subtitle entry chỉ định.
    /// </summary>
    public void DeleteSubtitle(SubtitleEntry target)
    {
        int idx = Subtitles.IndexOf(target);
        if (idx < 0) return;
        Subtitles.Remove(target);
        ReIndexSubtitles();
        // Chọn dòng kế tiếp (hoặc dòng cuối nếu xóa dòng cuối)
        if (Subtitles.Count > 0)
            SelectedSubtitle = Subtitles[Math.Min(idx, Subtitles.Count - 1)];
        StatusMessage = $"Đã xóa subtitle #{idx + 1}";
    }

    /// <summary>
    /// Đặt lại số thứ tự Index (1-based) cho tất cả subtitle sau insert/delete.
    /// </summary>
    private void ReIndexSubtitles()
    {
        for (int i = 0; i < Subtitles.Count; i++)
            Subtitles[i].Index = i + 1;
    }

    // =====================================================================
    // STEP 6: API COMMANDS (Async + SSE)
    // =====================================================================

    /// <summary>
    /// Chạy OCR pipeline trên video hiện tại.
    /// Flow: POST /api/v1/ocr → nhận task_id → stream SSE → update progress.
    /// </summary>
    [RelayCommand(CanExecute = nameof(CanRunTask))]
    private async Task RunOcr()
    {
        if (string.IsNullOrEmpty(VideoPath))
        {
            StatusMessage = "Vui lòng mở video trước.";
            return;
        }

        // Chuyển OcrRegion (tỉ lệ) -> pixel coords theo kích thước video gốc.
        // Nếu chưa đọc được size nguồn thì fallback về size hiển thị.
        var targetSize = VideoSourceSize.Width > 0 && VideoSourceSize.Height > 0
            ? VideoSourceSize
            : VideoViewSize;

        var regionPixels = targetSize.Width > 0
            ? OcrRegion.ToPixels(targetSize.Width, targetSize.Height)
            : new[] { 0, 0, 0, 0 };

        var task = await Api.StartOcrAsync(VideoPath, regionPixels);
        if (task == null) { StatusMessage = "Lỗi: Không thể bắt đầu OCR."; return; }

        await StreamTaskProgress(task.TaskId, onComplete: srtPath =>
        {
            // Load SRT vừa được tạo vào DataGrid
            if (!string.IsNullOrEmpty(srtPath))
            {
                CurrentSrtPath = srtPath;
                var entries = SubtitleService.Parse(srtPath);
                Subtitles.Clear();
                foreach (var e in entries) Subtitles.Add(e);
                StatusMessage = $"OCR hoàn tất: {entries.Count} dòng subtitle";
            }
        });
    }

    /// <summary>
    /// Dịch SRT hiện tại sang tiếng Việt.
    /// Flow: POST /api/v1/translate → nhận task_id → stream SSE → update progress.
    /// </summary>
    [RelayCommand(CanExecute = nameof(CanRunTask))]
    private async Task RunTranslate()
    {
        if (string.IsNullOrEmpty(CurrentSrtPath))
        {
            StatusMessage = "Vui lòng load file SRT trước.";
            return;
        }

        var glossary = ParseGlossary();
        var task = await Api.StartTranslateAsync(CurrentSrtPath, SelectedStyle, glossary);
        if (task == null) { StatusMessage = "Lỗi: Không thể bắt đầu dịch."; return; }

        await StreamTaskProgress(task.TaskId, onComplete: translatedPath =>
        {
            // Load SRT đã dịch vào DataGrid
            if (!string.IsNullOrEmpty(translatedPath))
            {
                CurrentSrtPath = translatedPath;
                var entries = SubtitleService.Parse(translatedPath);
                Subtitles.Clear();
                foreach (var e in entries) Subtitles.Add(e);
                StatusMessage = $"Dịch SRT hoàn tất: {entries.Count} dòng (chưa tạo audio CapCut)";
            }
        });
    }

    /// <summary>Load lại danh sách voice clones từ backend.</summary>
    [RelayCommand(CanExecute = nameof(CanRunTask))]
    private async Task RefreshVoices()
    {
        try
        {
            var voices = await Api.GetVoiceClonesAsync();
            VoiceClones.Clear();

            foreach (var voice in voices)
                VoiceClones.Add(voice);

            if (SelectedVoice == null && VoiceClones.Count > 0)
                SelectedVoice = VoiceClones[0];

            StatusMessage = $"Tìm thấy {voices.Count} voice clones";
        }
        catch (Exception ex)
        {
            StatusMessage = $"Lỗi load voices: {ex.Message}";
        }
    }

    /// <summary>
    /// Chạy STT: nhận dạng giọng nói từ video hiện tại bằng Fun-ASR-Nano.
    /// Flow: POST /api/v1/stt → task_id → poll status → load SRT vào DataGrid.
    /// </summary>
    [RelayCommand(CanExecute = nameof(CanRunTask))]
    private async Task RunStt()
    {
        if (string.IsNullOrEmpty(VideoPath))
        {
            StatusMessage = "Vui lòng mở video trước khi chạy STT.";
            return;
        }

        if (SttMaxCharsPerLine < 10 || SttMaxCharsPerLine > 120)
        {
            StatusMessage = "Số ký tự/dòng phải nằm trong khoảng 10–120.";
            return;
        }

        var task = await Api.StartSttAsync(
            videoPath: VideoPath,
            outputSrtPath: string.Empty,
            language: "中文",
            maxCharsPerLine: SttMaxCharsPerLine,
            silenceGapS: SttSilenceGapS);

        if (task == null)
        {
            StatusMessage = "Lỗi: Không thể bắt đầu STT. Kiểm tra backend đang chạy.";
            return;
        }

        await StreamTaskProgress(task.TaskId, onComplete: srtPath =>
        {
            if (!string.IsNullOrEmpty(srtPath) && System.IO.File.Exists(srtPath))
            {
                CurrentSrtPath = srtPath;
                var entries = SubtitleService.Parse(srtPath);
                Subtitles.Clear();
                foreach (var e in entries) Subtitles.Add(e);
                StatusMessage = $"STT hoàn tất (Fun-ASR-Nano): {entries.Count} dòng subtitle";
            }
        });
    }

    /// <summary>Chạy dubbing: TTS bằng OmniVoice rồi inject audio vào CapCut project.</summary>
    [RelayCommand(CanExecute = nameof(CanRunTask))]
    private async Task RunDubbing()
    {
        if (string.IsNullOrEmpty(CurrentSrtPath))
        {
            StatusMessage = "Vui lòng load SRT trước.";
            return;
        }

        if (SelectedVoice == null)
        {
            StatusMessage = "Vui lòng chọn voice clone.";
            return;
        }

        if (string.IsNullOrWhiteSpace(CapcutProjectName))
        {
            StatusMessage = "Vui lòng nhập tên project CapCut.";
            return;
        }

        if (SpeechRate < 0.5 || SpeechRate > 2.0)
        {
            StatusMessage = "Tốc độ đọc phải nằm trong khoảng 0.5x đến 2.0x.";
            return;
        }

        var task = await Api.StartDubbingAsync(
            srtPath: CurrentSrtPath,
            voiceId: SelectedVoice.Id,
            capcutProjectName: CapcutProjectName,
            speechRate: SpeechRate);

        if (task == null)
        {
            StatusMessage = "Lỗi: Không thể bắt đầu dubbing.";
            return;
        }

        await StreamTaskProgress(task.TaskId, onComplete: _ =>
        {
            StatusMessage =
                $"Đã chèn audio vào CapCut project '{CapcutProjectName}' (speed {SpeechRate:0.00}x)";
        });
    }

    /// <summary>
    /// Chuẩn hóa SRT: chọn file plain đã dịch, ghép timestamp từ ocr.srt cùng folder,
    /// tạo file SRT vietsub hoàn chỉnh và load vào DataGrid.
    /// </summary>
    [RelayCommand]
    private async Task MergeSrt()
    {
        var dialog = new OpenFileDialog
        {
            Title = "Chọn file plain đã dịch (index + text, không timestamp)",
            Filter = "Text files|*.txt|All files|*.*",
            CheckFileExists = true,
        };

        if (dialog.ShowDialog() != true) return;

        string plainPath = dialog.FileName;

        // Kiểm tra ocr.srt cùng folder
        string ocrSrtPath = System.IO.Path.Combine(
            System.IO.Path.GetDirectoryName(plainPath)!, "ocr.srt");
        if (!System.IO.File.Exists(ocrSrtPath))
        {
            StatusMessage = $"Không tìm thấy ocr.srt trong '{System.IO.Path.GetDirectoryName(plainPath)}'.";
            MessageBox.Show(
                $"Không tìm thấy file ocr.srt cùng thư mục với file plain đã dịch.\n" +
                $"Hãy đảm bảo file plain nằm cùng folder với ocr.srt:\n{ocrSrtPath}",
                "Thiếu ocr.srt",
                MessageBoxButton.OK,
                MessageBoxImage.Warning);
            return;
        }

        try
        {
            SetBusy(true);
            StatusMessage = "Đang ghép timestamp vào bản dịch...";

            var result = await Api.MergeSrtAsync(plainPath);
            if (result == null)
            {
                StatusMessage = "Lỗi: Backend không trả về kết quả.";
                return;
            }

            // Load file SRT kết quả vào DataGrid
            CurrentSrtPath = result.OutputPath;
            var entries = SubtitleService.Parse(result.OutputPath);
            Subtitles.Clear();
            foreach (var e in entries) Subtitles.Add(e);

            string skippedMsg = result.SkippedCount > 0
                ? $" (bỏ qua {result.SkippedCount} dòng không khớp index)"
                : string.Empty;
            StatusMessage = $"Chuẩn hóa SRT hoàn tất: {result.MergedCount} dòng{skippedMsg}";

            if (result.SkippedCount > 0)
            {
                MessageBox.Show(
                    $"Ghép thành công {result.MergedCount} dòng.\n" +
                    $"Bỏ qua {result.SkippedCount} dòng do không tìm thấy index tương ứng trong ocr.srt.\n" +
                    $"Các index bị bỏ: {string.Join(", ", result.SkippedIndices.Take(20))}",
                    "Chuẩn hóa SRT",
                    MessageBoxButton.OK,
                    MessageBoxImage.Information);
            }
        }
        catch (Exception ex)
        {
            StatusMessage = $"Lỗi chuẩn hóa SRT: {ex.Message}";
            MessageBox.Show(
                $"Lỗi khi ghép SRT:\n{ex.Message}",
                "Lỗi",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
        }
        finally
        {
            SetBusy(false);
        }
    }

    /// <summary>Chuẩn hóa SRT trước khi dịch: xuất plain txt (index + text, không timestamp)</summary>
    [RelayCommand]
    private async Task ExportPlainSubtitle()
    {
        string srtPath = CurrentSrtPath;

        // Nếu chưa có file SRT nào mở, cho chọn file
        if (string.IsNullOrEmpty(srtPath) || !System.IO.File.Exists(srtPath))
        {
            var dialog = new OpenFileDialog
            {
                Title = "Chọn file SRT cần chuẩn hóa trước khi dịch",
                Filter = "SRT files|*.srt|All files|*.*",
                CheckFileExists = true,
            };
            if (dialog.ShowDialog() != true) return;
            srtPath = dialog.FileName;
        }

        try
        {
            SetBusy(true);
            StatusMessage = "Đang xuất plain subtitle...";

            var result = await Api.ExportPlainSubtitleAsync(srtPath);
            if (result == null)
            {
                StatusMessage = "Lỗi: Backend không trả về kết quả.";
                return;
            }

            StatusMessage = $"Xuất xong {result.EntryCount} dòng → {result.OutputPath}";

            var ask = MessageBox.Show(
                $"Đã xuất {result.EntryCount} dòng plain subtitle.\n" +
                $"File: {result.OutputPath}\n\n" +
                "Bạn có muốn mở file vừa xuất bằng trình soạn thảo mặc định không?",
                "Chuẩn hóa trước khi dịch",
                MessageBoxButton.YesNo,
                MessageBoxImage.Information);

            if (ask == MessageBoxResult.Yes)
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
                {
                    FileName = result.OutputPath,
                    UseShellExecute = true,
                });
        }
        catch (Exception ex)
        {
            StatusMessage = $"Lỗi xuất plain subtitle: {ex.Message}";
            MessageBox.Show(
                $"Lỗi khi xuất:\n{ex.Message}",
                "Lỗi",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
        }
        finally
        {
            SetBusy(false);
        }
    }

    /// <summary>Hủy task đang chạy (OCR hoặc Translate)</summary>
    [RelayCommand(CanExecute = nameof(CanCancelTask))]
    private async Task CancelCurrentTask()
    {
        if (_currentTaskId == null) return;

        // Gọi API cancel + local cancel token
        await Api.CancelTaskAsync(_currentTaskId);
        _cancelSource?.Cancel();
        StatusMessage = "Đã hủy task.";
    }

    // ─ CanExecute guards —
    /// <summary>Chỉ chạy được khi không có task nào đang chạy</summary>
    private bool CanRunTask()  => !IsBusy;
    /// <summary>Chỉ cancel được khi đang có task chạy</summary>
    private bool CanCancelTask() => IsBusy;

    // ─ Core SSE streaming logic (dùng chung cho OCR / Translate / STT) ────
    /// <summary>
    /// Subscribe SSE stream của task — backend PUSH event khi có tiến độ mới.
    /// Dừng ngay khi nhận event "complete" hoặc "error" (không poll liên tục).
    /// </summary>
    private async Task StreamTaskProgress(string taskId, Action<string?>? onComplete = null)
    {
        _currentTaskId = taskId;
        _cancelSource  = new CancellationTokenSource();
        var ct         = _cancelSource.Token;

        // Bật busy mode: disable các nút, hiện progress bar
        SetBusy(true);

        try
        {
            // SSE stream: backend push events, FE lắng nghe 1 lần
            // Tự dừng khi nhận event type = "complete" hoặc "error"
            await foreach (var evt in Api.StreamTaskAsync(taskId, ct))
            {
                // Cập nhật progress và message trên UI
                TaskProgress = evt.Progress;
                if (!string.IsNullOrWhiteSpace(evt.Message))
                    StatusMessage = evt.Message;

                if (evt.Type == "complete")
                {
                    onComplete?.Invoke(evt.Result?.SrtPath);
                    break;  // Stream tự kết thúc, không cần poll thêm
                }

                if (evt.Type == "error")
                {
                    StatusMessage = $"Lỗi: {evt.Message}";
                    break;
                }
                // "progress" và "keepalive" → tiếp tục lắng nghe
            }
        }
        catch (OperationCanceledException)
        {
            // User hủy → không làm gì thêm
        }
        catch (Exception ex)
        {
            StatusMessage = $"Lỗi kết nối SSE: {ex.Message}";
        }
        finally
        {
            // Luôn tắt busy mode dù thành công hay thất bại
            SetBusy(false);
            _currentTaskId = null;
            _cancelSource?.Dispose();
            _cancelSource  = null;
        }
    }

    /// <summary>Bật/tắt busy mode và notify CanExecute cho các button</summary>
    private void SetBusy(bool busy)
    {
        IsBusy = busy;
        // Thông báo lại CanExecute để enable/disable buttons
        RunOcrCommand.NotifyCanExecuteChanged();
        RunTranslateCommand.NotifyCanExecuteChanged();
        RunDubbingCommand.NotifyCanExecuteChanged();
        RunSttCommand.NotifyCanExecuteChanged();
        MergeSrtCommand.NotifyCanExecuteChanged();
        ExportPlainSubtitleCommand.NotifyCanExecuteChanged();
        RefreshVoicesCommand.NotifyCanExecuteChanged();
        CancelCurrentTaskCommand.NotifyCanExecuteChanged();
    }

    /// <summary>Check backend health rồi update IsBackendConnected</summary>
    public async Task CheckBackendHealthAsync()
    {
        IsBackendConnected = await Api.CheckHealthAsync();
        StatusMessage = IsBackendConnected
            ? "Backend đang chạy (✓)"
            : "Backend chưa chạy — hãy chạy: python main.py";
    }

    public Dictionary<string, string> ParseGlossary()
    {
        var result = new Dictionary<string, string>();
        foreach (var line in GlossaryText.Split('\n', StringSplitOptions.RemoveEmptyEntries))
        {
            var parts = line.Split('=', 2);
            if (parts.Length == 2)
            {
                var key = parts[0].Trim();
                var val = parts[1].Trim();
                if (!string.IsNullOrEmpty(key))
                    result[key] = val;
            }
        }
        return result;
    }

    /// <summary>
    /// Tự động highlight dòng sub tương ứng với vị trí video hiện tại
    /// Gọi từ DispatcherTimer 100ms trong MainWindow.xaml.cs
    /// </summary>
    public void SyncSubtitleHighlight()
    {
        var currentMs = CurrentPositionMs;
        // Tìm dòng sub đang active (startTime ≤ current < endTime)
        var active = Subtitles.FirstOrDefault(s =>
            s.StartTime.TotalMilliseconds <= currentMs &&
            currentMs < s.EndTime.TotalMilliseconds);

        if (active != null && active != SelectedSubtitle)
            SelectedSubtitle = active;
    }
}
