// Views/MainWindow.xaml.cs — Code-behind của MainWindow

// Alias rõ ràng để tránh conflict:
// System.Windows.Media.MediaPlayer (WPF built-in) vs LibVLCSharp.Shared.MediaPlayer
using LibVLC         = LibVLCSharp.Shared.LibVLC;
using VlcMediaPlayer = LibVLCSharp.Shared.MediaPlayer;
using LibVLCSharp.Shared;           // Vẫn cần cho các types khác (Media, Core...)

using System.ComponentModel;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Media;         // Rectangle dùng Brush, không dùng MediaPlayer
using System.Windows.Shapes;
using System.Windows.Threading;
using VideoLocalizer.Models;
using VideoLocalizer.ViewModels;

namespace VideoLocalizer.Views;

public partial class MainWindow : Wpf.Ui.Controls.FluentWindow
{
    // ── LibVLC objects ──
    private LibVLC? _libVlc;
    private VlcMediaPlayer? _mediaPlayer;

    // ── Timer 100ms: đồng bộ highlight sub với video ──
    private readonly DispatcherTimer _syncTimer;

    // ── Để tránh SeekSlider loop khi code cập nhật giá trị ──
    private bool _isSeeking = false;

    // ── Cache độ dài video (ms) để seek vẫn hoạt động khi video Stopped ──
    private long _videoLength = 0;

    // ── OCR Region Selection state ──
    /// <summary>true khi đang ở chế độ chọn vùng OCR</summary>
    private bool _isOcrSelectionMode = false;
    /// <summary>OcrRegion hiện tại (tầ lệ 0–1)</summary>
    private OcrRegion _ocrRegion = OcrRegion.Default;
    /// <summary>Vị trí bắt đầu drag khi đang vẽ vùng</summary>
    private System.Windows.Point _ocrDragStart;

    // Truy cập ViewModel từ DataContext
    private MainViewModel VM => (MainViewModel)DataContext;

    public MainWindow()
    {
        InitializeComponent();

        // Khởi tạo LibVLC (phải gọi Core.Initialize() một lần)
        Core.Initialize();
        _libVlc = new LibVLC();
        _mediaPlayer = new VlcMediaPlayer(_libVlc);

        // Gán MediaPlayer vào VideoView control
        VideoView.MediaPlayer = _mediaPlayer;

        // Subscribe events của MediaPlayer để update UI
        _mediaPlayer.Playing     += OnMediaPlaying;
        _mediaPlayer.Paused      += OnMediaPaused;
        _mediaPlayer.Stopped     += OnMediaStopped;
        _mediaPlayer.TimeChanged += OnTimeChanged;

        // Watch ViewModel.VideoPath: khi user chọn video → load vào LibVLC
        // Watch cùng health check — dùng Loaded event vì DataContext chưa có trong constructor
        Loaded += async (_, _) =>
        {
            VM.PropertyChanged += OnVmPropertyChanged;

            // Kiểm tra backend khi khởi động (non-blocking)
            await VM.CheckBackendHealthAsync();
        };

        // Timer 100ms: liên tục check vị trí video → highlight sub
        _syncTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(100) };
        _syncTimer.Tick += SyncTimer_Tick;
        _syncTimer.Start();
    }

    /// <summary>
    /// Watch các property thay đổi từ ViewModel
    /// Hiện tại: VideoPath — khi đổi thì load video vào LibVLC
    /// </summary>
    private void OnVmPropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(VM.VideoPath) && !string.IsNullOrEmpty(VM.VideoPath))
        {
            LoadVideoIntoPlayer(VM.VideoPath);
        }
    }

    /// <summary>
    /// Load file video vào LibVLC MediaPlayer và bắt đầu phát
    /// </summary>
    private void LoadVideoIntoPlayer(string path)
    {
        if (_libVlc == null || _mediaPlayer == null) return;

        // Tạo Media mới từ đường dẫn file
        var media = new Media(_libVlc, new Uri(path));
        _mediaPlayer.Media = media;
        media.Dispose(); // LibVLC giữ reference riêng, có thể dispose ngay

        _videoLength = 0; // Reset cache — sẽ update từ OnTimeChanged
        _mediaPlayer.Play();
        VM.StatusMessage = $"Đang phát: {System.IO.Path.GetFileName(path)}";
    }

    // ═══════════════════════════════════════════════
    // MENU HANDLERS
    // ═══════════════════════════════════════════════

    private void MenuExit_Click(object sender, RoutedEventArgs e)
    {
        Application.Current.Shutdown();
    }

    private void MenuSelectOcrRegion_Click(object sender, RoutedEventArgs e)
    {
        _isOcrSelectionMode = MenuSelectOcrRegion.IsChecked;

        if (_isOcrSelectionMode)
        {
            // Giải pháp đơn giản cho AirSpace problem (không cần snapshot):
            // 1. Ẩn VideoView (native HWND) ngay lập tức — synchronous, không lag
            VideoView.Visibility    = Visibility.Hidden;
            // 2. Hiện dark overlay với hướng dẫn
            OcrPlaceholder.Visibility = Visibility.Visible;
            // 3. Bật Canvas nhận mouse events (hoạt động vì không còn HWND bên dưới)
            OcrCanvas.IsHitTestVisible = true;

            _mediaPlayer?.Pause(); // Pause nhẹ nhàng, không block UI
            VM.StatusMessage = "🖱 Kéo chuột để chọn vùng subtitle, thả chuột khi xong";
        }
        else
        {
            RestoreVideoView();
            VM.StatusMessage = $"Vùng OCR: {_ocrRegion}";
        }
    }

    /// <summary>Restore VideoView, ẩn overlay — dùng sau khi chọn xong hoặc hủy</summary>
    private void RestoreVideoView()
    {
        OcrCanvas.IsHitTestVisible    = false;
        OcrPlaceholder.Visibility     = Visibility.Collapsed;
        VideoView.Visibility          = Visibility.Visible;
        MenuSelectOcrRegion.IsChecked = false;
        _isOcrSelectionMode           = false;
    }

    private void MenuOcr_Click(object sender, RoutedEventArgs e)
    {
        // Gọi thẳng RunOcrCommand — giống bấm nút "Chạy OCR" trên toolbar
        // Nếu chưa chọn vùng, backend sẽ dùng full frame [0,0,0,0] làm fallback
        if (VM.RunOcrCommand.CanExecute(null))
            VM.RunOcrCommand.Execute(null);
    }

    private void MenuTranslate_Click(object sender, RoutedEventArgs e)
    {
        // TODO Step 6: gọi ApiService.StartTranslate()
        MessageBox.Show("Translate feature coming in Step 6!", "Info");
    }

    private void MenuSettings_Click(object sender, RoutedEventArgs e)
    {
        // TODO Step 10: mở SettingsWindow
        MessageBox.Show("Settings coming in Step 10!", "Info");
    }

    // ═══════════════════════════════════════════════
    // =======================================================
    // OCR REGION SELECTION — Canvas mouse drag handlers
    // =======================================================

    private void OcrCanvas_MouseDown(object sender, MouseButtonEventArgs e)
    {
        if (!_isOcrSelectionMode) return;

        // Lưu vị trí bắt đầu drag
        _ocrDragStart = e.GetPosition(OcrCanvas);

        // Ẩn rectangle cũ trong lúc đang vẽ mới
        OcrSelectionRect.Visibility = Visibility.Collapsed;
        OcrLabelBorder.Visibility   = Visibility.Collapsed;

        // Bắt đầu capture mouse để nhận MouseMove dù ra ngoài Canvas
        OcrCanvas.CaptureMouse();
    }

    private void OcrCanvas_MouseMove(object sender, MouseEventArgs e)
    {
        if (!_isOcrSelectionMode || e.LeftButton != MouseButtonState.Pressed) return;

        var current = e.GetPosition(OcrCanvas);

        // Tính toạ độ rectangle (đảm bảo X, Y luôn là góc trên trái)
        double x = Math.Min(_ocrDragStart.X, current.X);
        double y = Math.Min(_ocrDragStart.Y, current.Y);
        double w = Math.Abs(current.X - _ocrDragStart.X);
        double h = Math.Abs(current.Y - _ocrDragStart.Y);

        // Vẽ rectangle lên Canvas
        Canvas.SetLeft(OcrSelectionRect, x);
        Canvas.SetTop(OcrSelectionRect, y);
        OcrSelectionRect.Width  = w;
        OcrSelectionRect.Height = h;
        OcrSelectionRect.Visibility = Visibility.Visible;
    }

    private void OcrCanvas_MouseUp(object sender, MouseButtonEventArgs e)
    {
        if (!_isOcrSelectionMode) return;
        OcrCanvas.ReleaseMouseCapture();

        var current = e.GetPosition(OcrCanvas);
        double x = Math.Min(_ocrDragStart.X, current.X);
        double y = Math.Min(_ocrDragStart.Y, current.Y);
        double w = Math.Abs(current.X - _ocrDragStart.X);
        double h = Math.Abs(current.Y - _ocrDragStart.Y);

        var videoRect = GetVideoContentRectInCanvas();
        var selectionRect = new Rect(x, y, w, h);
        var clippedRect = Rect.Intersect(selectionRect, videoRect);

        if (clippedRect.IsEmpty || clippedRect.Width < 4 || clippedRect.Height < 4)
        {
            VM.StatusMessage = "Vùng chọn nằm ngoài khung video hiển thị. Hãy chọn lại.";
            OcrSelectionRect.Visibility = Visibility.Collapsed;
            OcrLabelBorder.Visibility = Visibility.Collapsed;
            return;
        }

        // Vẽ lại rect theo vùng đã clip vào khung video thực tế.
        Canvas.SetLeft(OcrSelectionRect, clippedRect.X);
        Canvas.SetTop(OcrSelectionRect, clippedRect.Y);
        OcrSelectionRect.Width = clippedRect.Width;
        OcrSelectionRect.Height = clippedRect.Height;
        OcrSelectionRect.Visibility = Visibility.Visible;

        // Lưu OcrRegion theo tỉ lệ bên trong nội dung video (không tính viền đen letterbox).
        _ocrRegion = OcrRegion.FromPixels(
            pxX: clippedRect.X - videoRect.X,
            pxY: clippedRect.Y - videoRect.Y,
            pxW: clippedRect.Width,
            pxH: clippedRect.Height,
            controlWidth: videoRect.Width,
            controlHeight: videoRect.Height
        );
        VM.OcrRegion = _ocrRegion;

        // Hiện label "OCR Region" ở góc trên của hộp chọn
        Canvas.SetLeft(OcrLabelBorder, clippedRect.X + 4);
        Canvas.SetTop(OcrLabelBorder, clippedRect.Y + 4);
        OcrLabelBorder.Visibility = Visibility.Visible;

        VM.StatusMessage = $"✅ OCR region: {_ocrRegion} (khung video: {videoRect.Width:0}x{videoRect.Height:0})";

        // Restore VideoView (ẩn overlay, hiện lại HWND)
        RestoreVideoView();
    }

    // ═══════════════════════════════════════════════

    // ═══════════════════════════════════════════════
    // VIDEO PLAYER CONTROLS
    // ═══════════════════════════════════════════════

    private void BtnPlayPause_Click(object sender, RoutedEventArgs e)
    {
        if (_mediaPlayer == null) return;

        if (_mediaPlayer.IsPlaying)
            _mediaPlayer.Pause();
        else
            _mediaPlayer.Play();
    }

    private void SeekSlider_MouseDown(object sender, System.Windows.Input.MouseButtonEventArgs e)
    {
        // User bắt đầu kéo slider → pause timer để không bị loop
        _isSeeking = true;
    }

    private void SeekSlider_MouseUp(object sender, System.Windows.Input.MouseButtonEventArgs e)
    {
        // User thả slider → seek đến vị trí mới
        if (_mediaPlayer != null && _mediaPlayer.Length > 0)
        {
            long targetMs = (long)(SeekSlider.Value * _mediaPlayer.Length);
            _mediaPlayer.Time = targetMs;
        }
        _isSeeking = false;
    }

    private void VolumeSlider_ValueChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (_mediaPlayer != null)
            _mediaPlayer.Volume = (int)VolumeSlider.Value;
    }

    // ─ Bước 1: Sau khi Slider render xong, attach Thumb events —
    // Lý do: Thumb là visual child của Slider, chưa có lúc khai báo XAML
    private void SeekSlider_Loaded(object sender, RoutedEventArgs e)
    {
        // Tìm Track (visual child của Slider chứa Thumb bên trong)
        var track = SeekSlider.Template.FindName("PART_Track", SeekSlider) as Track;
        var thumb = track?.Thumb;

        if (thumb != null)
        {
            // DragStarted: user bắt đầu kéo thumb
            thumb.DragStarted   += SeekThumb_DragStarted;
            // DragCompleted: user nhả thumb
            thumb.DragCompleted += SeekThumb_DragCompleted;
        }

        // Click-on-TRACK (không phải drag thumb): bắt bằng MouseLeftButtonUp
        // Với IsMoveToPointEnabled=True, Slider đã nhảy đúng vị trí trước khi event này fire
        SeekSlider.AddHandler(
            UIElement.MouseLeftButtonUpEvent,
            new MouseButtonEventHandler(SeekSlider_TrackClicked),
            handledEventsToo: true   // cần true vì Slider đã mark event là handled
        );
    }

    // — Bước 2a: User bắt đầu kéo thumb —
    private void SeekThumb_DragStarted(object sender, DragStartedEventArgs e)
    {
        _isSeeking = true;  // Dừng cập nhật SeekSlider từ TimeChanged
    }

    // — Bước 2b: User nhả thumb sau khi kéo —
    private void SeekThumb_DragCompleted(object sender, DragCompletedEventArgs e)
    {
        PerformSeek();      // Seek đến vị trí mới
        _isSeeking = false;
    }

    // — Bước 2c: User click vào track (không kéo) —
    private void SeekSlider_TrackClicked(object sender, MouseButtonEventArgs e)
    {
        // Slider đã update Value nhờ IsMoveToPointEnabled, ta chỉ cần seek
        PerformSeek();
    }

    // — Core seek logic dùng chung cho cả drag và click —
    private void PerformSeek()
    {
        if (_mediaPlayer == null) return;
        
        // Ưu tiên dùng cache _videoLength để seek vẫn hoạt động khi video Stopped
        long length = _videoLength > 0 ? _videoLength : _mediaPlayer.Length;
        if (length <= 0) return;    // Chưa load xong, bỏ qua

        long targetMs = (long)(SeekSlider.Value * length);
        _mediaPlayer.Time = targetMs;

        // Tự động play lại sau seek (quan trọng khi video vừa kết thúc và user muốn rewind)
        if (!_mediaPlayer.IsPlaying)
        {
            _mediaPlayer.Play();
        }
    }

    // ── Click dòng sub trên DataGrid → seek video đến timestamp ──
    private void SubtitleGrid_SelectionChanged(object sender,
        System.Windows.Controls.SelectionChangedEventArgs e)
    {
        // Xử lý ở Step 8 (video sync)
    }

    // BtnRunOcr và BtnTranslate giờ dùng Command binding (RunOcrCommand / RunTranslateCommand)
    // không cần Click handlers nữa

    // ═══════════════════════════════════════════════
    // MEDIAPLAYER EVENT HANDLERS
    // (chạy trên thread khác → dùng Dispatcher.Invoke để update UI)
    // ═══════════════════════════════════════════════

    private void OnMediaPlaying(object? sender, EventArgs e)
    {
        Dispatcher.Invoke(() =>
        {
            // Đổi icon nút thành Pause
            BtnPlayPause.Icon = new Wpf.Ui.Controls.SymbolIcon(Wpf.Ui.Controls.SymbolRegular.Pause24);
            VM.StatusMessage = "Đang phát...";
        });
    }

    private void OnMediaPaused(object? sender, EventArgs e)
    {
        Dispatcher.Invoke(() =>
        {
            BtnPlayPause.Icon = new Wpf.Ui.Controls.SymbolIcon(Wpf.Ui.Controls.SymbolRegular.Play24);
            VM.StatusMessage = "Tạm dừng";
        });
    }

    private void OnMediaStopped(object? sender, EventArgs e)
    {
        Dispatcher.Invoke(() =>
        {
            BtnPlayPause.Icon = new Wpf.Ui.Controls.SymbolIcon(Wpf.Ui.Controls.SymbolRegular.Play24);
            VM.StatusMessage = "Đã dừng";
            // Đảm bảo Slider vẫn có thể dùng để seek lại (rewind)
            SeekSlider.IsEnabled = true;
        });
    }

    private void OnTimeChanged(object? sender, MediaPlayerTimeChangedEventArgs e)
    {
        // Cập nhật SeekSlider và label thời gian
        Dispatcher.Invoke(() =>
        {
            if (!_isSeeking && _mediaPlayer!.Length > 0)
            {
                // Cache độ dài video để dùng sau khi video Stopped
                if (_videoLength == 0)
                    _videoLength = _mediaPlayer.Length;

                SeekSlider.Value = _videoLength > 0 ? (double)e.Time / _videoLength : 0;

                // Format thời gian "mm:ss / mm:ss"
                var cur = TimeSpan.FromMilliseconds(e.Time);
                var tot = TimeSpan.FromMilliseconds(_videoLength);
                TxtTime.Text = $"{cur:mm\\:ss} / {tot:mm\\:ss}";

                // Cập nhật vị trí cho ViewModel (dùng highlight sub)
                VM.CurrentPositionMs = e.Time;
            }
        });
    }

    // ═══════════════════════════════════════════════
    // SYNC TIMER: cứ 100ms highlight dòng sub active
    // ═══════════════════════════════════════════════

    private void SyncTimer_Tick(object? sender, EventArgs e)
    {
        VM.SyncSubtitleHighlight();

        // Cuộn DataGrid để luôn hiện dòng đang active
        if (VM.SelectedSubtitle != null)
            SubtitleGrid.ScrollIntoView(VM.SelectedSubtitle);

        // Kích thước khung hiển thị video bên trong control (loại trừ letterbox)
        var videoRect = GetVideoContentRectInCanvas();
        VM.VideoViewSize = new System.Windows.Size(
            videoRect.Width, videoRect.Height);

        // Kích thước nguồn video gốc để convert OcrRegion -> pixel gửi backend.
        if (TryGetVideoSourceSize(out var sourceW, out var sourceH))
        {
            VM.VideoSourceSize = new System.Windows.Size(sourceW, sourceH);
        }
    }

    private Rect GetVideoContentRectInCanvas()
    {
        double canvasW = OcrCanvas.ActualWidth;
        double canvasH = OcrCanvas.ActualHeight;
        if (canvasW <= 0 || canvasH <= 0)
            return new Rect(0, 0, Math.Max(0, canvasW), Math.Max(0, canvasH));

        if (!TryGetVideoSourceSize(out var sourceW, out var sourceH))
            return new Rect(0, 0, canvasW, canvasH);

        double videoAspect = sourceW / sourceH;
        double canvasAspect = canvasW / canvasH;

        if (canvasAspect > videoAspect)
        {
            // Canvas rộng hơn video -> có cột đen trái/phải.
            double renderH = canvasH;
            double renderW = renderH * videoAspect;
            double offsetX = (canvasW - renderW) / 2.0;
            return new Rect(offsetX, 0, renderW, renderH);
        }

        // Canvas cao hơn video -> có viền đen trên/dưới.
        double fittedW = canvasW;
        double fittedH = fittedW / videoAspect;
        double offsetY = (canvasH - fittedH) / 2.0;
        return new Rect(0, offsetY, fittedW, fittedH);
    }

    private bool TryGetVideoSourceSize(out double width, out double height)
    {
        width = 0;
        height = 0;

        if (_mediaPlayer == null)
            return false;

        try
        {
            uint w = 0;
            uint h = 0;
            if (_mediaPlayer.Size(0, ref w, ref h) && w > 0 && h > 0)
            {
                width = w;
                height = h;
                return true;
            }
        }
        catch
        {
            return false;
        }

        return false;
    }

    // ═══════════════════════════════════════════════
    // SUBTITLE CONTEXT MENU HANDLERS
    // ═══════════════════════════════════════════════

    /// <summary>
    /// Cập nhật trạng thái menu Xóa: chỉ enable khi có dòng đang chọn
    /// </summary>
    private void SubtitleContextMenu_Opened(object sender, RoutedEventArgs e)
    {
        bool hasSelection = VM.SelectedSubtitle != null;
        CtxAddBefore.IsEnabled = hasSelection || VM.Subtitles.Count == 0;
        CtxAddAfter.IsEnabled  = hasSelection || VM.Subtitles.Count == 0;
        CtxDelete.IsEnabled    = hasSelection;
    }

    /// <summary>
    /// Context menu "Thêm trước": mở dialog rồi chèn entry mới trước dòng đang chọn
    /// </summary>
    private void CtxAddBefore_Click(object sender, RoutedEventArgs e)
    {
        var target = VM.SelectedSubtitle;
        var newEntry = ShowAddDialog();
        if (newEntry == null) return;

        if (target != null)
            VM.AddSubtitleBefore(target, newEntry);
        else
        {
            // Danh sách rỗng — thêm vào đầu
            VM.Subtitles.Add(newEntry);
            VM.SelectedSubtitle = newEntry;
        }
    }

    /// <summary>
    /// Context menu "Thêm sau": mở dialog rồi chèn entry mới sau dòng đang chọn
    /// </summary>
    private void CtxAddAfter_Click(object sender, RoutedEventArgs e)
    {
        var target = VM.SelectedSubtitle;
        var newEntry = ShowAddDialog();
        if (newEntry == null) return;

        if (target != null)
            VM.AddSubtitleAfter(target, newEntry);
        else
        {
            VM.Subtitles.Add(newEntry);
            VM.SelectedSubtitle = newEntry;
        }
    }

    /// <summary>
    /// Context menu "Xóa": xóa dòng đang chọn
    /// </summary>
    private void CtxDelete_Click(object sender, RoutedEventArgs e)
    {
        var target = VM.SelectedSubtitle;
        if (target == null) return;

        var answer = MessageBox.Show(
            $"Xóa subtitle #{target.Index}?\n\"{target.Text}\"",
            "Xác nhận xóa",
            MessageBoxButton.YesNo,
            MessageBoxImage.Question);

        if (answer == MessageBoxResult.Yes)
            VM.DeleteSubtitle(target);
    }

    /// <summary>
    /// Mở AddSubtitleDialog với StartTime = vị trí video hiện tại.
    /// Trả về SubtitleEntry mới hoặc null nếu user hủy.
    /// </summary>
    private SubtitleEntry? ShowAddDialog()
    {
        var dialog = new AddSubtitleDialog(_mediaPlayer?.Time ?? 0)
        {
            Owner = this
        };
        return dialog.ShowDialog() == true ? dialog.Result : null;
    }

    // ═══════════════════════════════════════════════
    // F4: STAMP CURRENT VIDEO POSITION → StartTime / EndTime
    // ═══════════════════════════════════════════════

    /// <summary>
    /// F4 khi DataGrid đang focus:
    ///  - Nếu đang edit cột StartTime hoặc EndTime → ghi vị trí video hiện tại vào ô đó
    ///  - Nếu không đang edit → ghi vào EndTime của dòng đang chọn (tiện nhất khi xem video)
    ///
    /// Hướng dẫn dùng:
    ///   1. Double-click vào ô EndTime → cell vào chế độ edit
    ///   2. Play video, lắng nghe đến lúc subtitle kết thúc
    ///   3. Bấm F4 → End time được điền ngay lập tức
    /// </summary>
    private void SubtitleGrid_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key != Key.F4) return;

        var selected = VM.SelectedSubtitle;
        if (selected == null) return;

        long posMs = _mediaPlayer?.Time ?? 0;
        var  posTs = TimeSpan.FromMilliseconds(posMs);

        // Kiểm tra cell nào đang được edit
        var editingColumn = SubtitleGrid.CurrentColumn;
        if (editingColumn != null)
        {
            string? header = editingColumn.Header?.ToString();

            if (header == "Bắt đầu")
            {
                // Kết thúc edit hiện tại → cập nhật giá trị mới → vào edit lại
                SubtitleGrid.CommitEdit(DataGridEditingUnit.Cell, exitEditingMode: true);
                selected.StartTime = posTs;
                VM.StatusMessage = $"StartTime → {FormatTs(posTs)} (F4)";
                e.Handled = true;
                return;
            }

            if (header == "Kết thúc")
            {
                SubtitleGrid.CommitEdit(DataGridEditingUnit.Cell, exitEditingMode: true);
                selected.EndTime = posTs;
                VM.StatusMessage = $"EndTime → {FormatTs(posTs)} (F4)";
                e.Handled = true;
                return;
            }
        }

        // Không đang edit cụ thể → mặc định stamp vào EndTime
        SubtitleGrid.CommitEdit(DataGridEditingUnit.Row, exitEditingMode: true);
        selected.EndTime = posTs;
        VM.StatusMessage = $"EndTime → {FormatTs(posTs)} (F4)";
        e.Handled = true;
    }

    /// <summary>Format TimeSpan → "hh:mm:ss,fff" để hiển thị status</summary>
    private static string FormatTs(TimeSpan ts) =>
        $"{(int)ts.TotalHours:D2}:{ts.Minutes:D2}:{ts.Seconds:D2},{ts.Milliseconds:D3}";

    // ═══════════════════════════════════════════════
    // SUBTITLE SYNC: double-click dòng sub → seek video
    // ═══════════════════════════════════════════════

    /// <summary>
    /// Double-click dòng sub trên DataGrid → seek video đến StartTime của dòng đó.
    /// Giúp user xem thử context xung quanh subtitle đang edit.
    /// </summary>
    private void SubtitleGrid_MouseDoubleClick(object sender, MouseButtonEventArgs e)
    {
        if (_mediaPlayer == null) return;
        if (VM.SelectedSubtitle == null) return;

        // Seek đến timestamp bắt đầu của subtitle đang chọn
        long targetMs = (long)VM.SelectedSubtitle.StartTime.TotalMilliseconds;
        _mediaPlayer.Time = targetMs;

        // Phát nếu đang dừng
        if (!_mediaPlayer.IsPlaying)
            _mediaPlayer.Play();
    }

    // ═══════════════════════════════════════════════
    // CLEANUP khi đóng cửa sổ
    // ═══════════════════════════════════════════════

    protected override void OnClosed(EventArgs e)
    {
        _syncTimer.Stop();
        _mediaPlayer?.Stop();
        _mediaPlayer?.Dispose();
        _libVlc?.Dispose();
        base.OnClosed(e);
    }
}
