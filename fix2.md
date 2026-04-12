# Implementation Plan: 4 Major Improvements

## Tổng quan

4 thay đổi lớn cần thực hiện:

| # | Task | Phạm vi | Độ phức tạp |
|---|------|---------|-------------|
| 1 | Fix crop UI bị đen khi chọn vùng OCR | Frontend (WPF) | Thấp |
| 2 | Pause video khi click vào dòng subtitle | Frontend (WPF) | Thấp |
| 3 | Thay edge-tts bằng OmniVoice (voice cloning) | Backend + Frontend | Cao |
| 4 | Thay WhisperX bằng Qwen3-ASR + ForcedAligner | Backend + Frontend | Trung bình |

---

## Task 1: Fix crop UI — Hiện snapshot thay vì màn hình đen

### Vấn đề hiện tại

Khi bật chế độ "Chọn vùng OCR", code hiện tại **ẩn hoàn toàn VideoView** (HWND) và hiện một overlay đen (`OcrPlaceholder`). Lý do ban đầu là giải quyết WPF AirSpace problem (Canvas WPF không overlay được lên native HWND). Tuy nhiên, user không nhìn thấy video frame nên trải nghiệm rất tệ — không biết subtitle nằm ở đâu.

### Giải pháp

**Chụp snapshot video frame hiện tại** trước khi ẩn VideoView, hiển thị snapshot đó trong `OcrPlaceholder` để user thấy rõ vị trí subtitle.

LibVLCSharp hỗ trợ `TakeSnapshot()` — chụp frame hiện tại thành file ảnh. Ta sẽ:
1. Gọi `_mediaPlayer.TakeSnapshot(0, snapshotPath, 0, 0)` để chụp frame
2. Load ảnh snapshot vào một `Image` control bên trong `OcrPlaceholder`
3. User kéo chọn vùng OCR trên ảnh snapshot thay vì overlay đen

### Proposed Changes

#### [MODIFY] [MainWindow.xaml](file:///e:/AI-Video_Localizer/src/VideoLocalizer.App/Views/MainWindow.xaml)

Thay đổi `OcrPlaceholder` từ Border với text hướng dẫn thành Image + text overlay:

```diff
-<Border Name="OcrPlaceholder"
-        Background="#DD111111"
-        Visibility="Collapsed">
-    <StackPanel HorizontalAlignment="Center" VerticalAlignment="Center">
-        <TextBlock Text="🖱 Kéo chuột để khoanh vùng có subtitle"
-                   .../>
-        ...
-    </StackPanel>
-</Border>
+<Grid Name="OcrPlaceholder" Visibility="Collapsed">
+    <!-- Snapshot frame hiển thị -->
+    <Image Name="OcrSnapshotImage"
+           Stretch="Uniform"
+           HorizontalAlignment="Center"
+           VerticalAlignment="Center"/>
+    <!-- Semi-transparent overlay + text hướng dẫn -->
+    <Border Background="#44000000">
+        <StackPanel HorizontalAlignment="Center" VerticalAlignment="Center">
+            <TextBlock Text="🖱 Kéo chuột để khoanh vùng có subtitle"
+                       Foreground="White" FontSize="15" FontWeight="SemiBold"
+                       HorizontalAlignment="Center"/>
+            <TextBlock Text="(thường ở 70–90% chiều cao video)"
+                       Foreground="#AAAAAA" FontSize="12" Margin="0,6,0,0"
+                       HorizontalAlignment="Center"/>
+            <TextBlock Text="Nhấn Esc hoặc bỏ tick menu để hủy"
+                       Foreground="#888888" FontSize="11" Margin="0,4,0,0"
+                       HorizontalAlignment="Center"/>
+        </StackPanel>
+    </Border>
+</Grid>
```

#### [MODIFY] [MainWindow.xaml.cs](file:///e:/AI-Video_Localizer/src/VideoLocalizer.App/Views/MainWindow.xaml.cs)

Cập nhật `MenuSelectOcrRegion_Click` — chụp snapshot trước khi ẩn VideoView:

```csharp
private void MenuSelectOcrRegion_Click(object sender, RoutedEventArgs e)
{
    _isOcrSelectionMode = MenuSelectOcrRegion.IsChecked;

    if (_isOcrSelectionMode)
    {
        // 1. Pause video
        _mediaPlayer?.Pause();

        // 2. Chụp snapshot frame hiện tại
        var snapshotPath = System.IO.Path.Combine(
            System.IO.Path.GetTempPath(), "avl_ocr_snapshot.png");
        bool snapshotOk = _mediaPlayer?.TakeSnapshot(0, snapshotPath, 0, 0) ?? false;

        if (snapshotOk && System.IO.File.Exists(snapshotPath))
        {
            // Load snapshot vào Image control
            var bitmap = new System.Windows.Media.Imaging.BitmapImage();
            bitmap.BeginInit();
            bitmap.CacheOption = System.Windows.Media.Imaging.BitmapCacheOption.OnLoad;
            bitmap.UriSource = new Uri(snapshotPath);
            bitmap.EndInit();
            OcrSnapshotImage.Source = bitmap;
        }

        // 3. Ẩn VideoView (HWND), hiện snapshot overlay
        VideoView.Visibility = Visibility.Hidden;
        OcrPlaceholder.Visibility = Visibility.Visible;
        OcrCanvas.IsHitTestVisible = true;

        VM.StatusMessage = "🖱 Kéo chuột để chọn vùng subtitle, thả chuột khi xong";
    }
    else
    {
        RestoreVideoView();
        VM.StatusMessage = $"Vùng OCR: {_ocrRegion}";
    }
}
```

> [!NOTE]
> `TakeSnapshot` ghi file nên cần khoảng ~50ms. Tuy nhiên, video đã pause nên không ảnh hưởng UX. Nếu snapshot thất bại (hiếm), overlay đen sẽ hiện thay vì crash.

---

## Task 2: Pause video khi click vào dòng subtitle

### Vấn đề hiện tại

Khi user click vào dòng subtitle trên DataGrid, `SubtitleGrid_SelectionChanged` hiện tại không làm gì. Video tiếp tục phát → dòng sub bị highlight liên tục thay đổi bởi `SyncTimer` → rất khó edit.

Hành vi double-click ([SubtitleGrid_MouseDoubleClick](file:///e:/AI-Video_Localizer/src/VideoLocalizer.App/Views/MainWindow.xaml.cs#L670-L682)) lại seek + play, ngược với mục đích edit.

### Giải pháp

- **Single-click** vào dòng sub → seek video đến StartTime + **pause** → user có thể chỉnh sửa text, timestamp
- **Double-click** → giữ nguyên seek + play (xem preview context)
- `SyncSubtitleHighlight` phải **không override** selection khi video đang pause (tránh loop)

### Proposed Changes

#### [MODIFY] [MainWindow.xaml.cs](file:///e:/AI-Video_Localizer/src/VideoLocalizer.App/Views/MainWindow.xaml.cs)

```diff
 // ── Click dòng sub trên DataGrid → seek video đến timestamp ──
 private void SubtitleGrid_SelectionChanged(object sender,
     System.Windows.Controls.SelectionChangedEventArgs e)
 {
-    // Xử lý ở Step 8 (video sync)
+    if (_mediaPlayer == null) return;
+    if (VM.SelectedSubtitle == null) return;
+
+    // Chỉ xử lý khi user thực sự click — bỏ qua khi SyncTimer đổi selection
+    if (_isSyncTimerUpdating) return;
+
+    // Seek đến thời điểm bắt đầu của subtitle
+    long targetMs = (long)VM.SelectedSubtitle.StartTime.TotalMilliseconds;
+    _mediaPlayer.Time = targetMs;
+
+    // PAUSE video để user có thể edit SRT
+    if (_mediaPlayer.IsPlaying)
+        _mediaPlayer.Pause();
 }
```

Thêm flag `_isSyncTimerUpdating` để phân biệt user click vs auto-sync:

```diff
+private bool _isSyncTimerUpdating = false;
```

Cập nhật `SyncTimer_Tick` — chỉ highlight khi đang phát, và set flag:

```diff
 private void SyncTimer_Tick(object? sender, EventArgs e)
 {
+    // Chỉ tự động sync highlight khi video đang phát
+    // Khi pause (user đang edit), giữ nguyên selection
+    if (_mediaPlayer != null && _mediaPlayer.IsPlaying)
+    {
+        _isSyncTimerUpdating = true;
+        VM.SyncSubtitleHighlight();
+        _isSyncTimerUpdating = false;
+    }
-    VM.SyncSubtitleHighlight();
 
     // Cuộn DataGrid...
```
---