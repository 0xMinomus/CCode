<#
CCode Windows Computer Use helper. One long-lived process per MCP session, speaking NDJSON on
stdin/stdout: {"id":N,"op":"...","args":{...}} in, {"id":N,"ok":true,"data":{...}} out.
The Add-Type block below is compiled once at startup, so a click never pays for a new process.

Capture is System.Drawing (CopyFromScreen); input is SendInput; text and elements come from UI
Automation; the pointer comes from GetCursorPos. This process is not elevated, so UIPI blocks
input to elevated windows: that is reported as an explicit error, never worked around.
#>
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

Add-Type -Language CSharp -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class CCodeWin {
  public const uint INPUT_MOUSE = 0, INPUT_KEYBOARD = 1;
  public const uint MOUSEEVENTF_LEFTDOWN = 0x0002, MOUSEEVENTF_LEFTUP = 0x0004;
  public const uint MOUSEEVENTF_RIGHTDOWN = 0x0008, MOUSEEVENTF_RIGHTUP = 0x0010;
  public const uint MOUSEEVENTF_MIDDLEDOWN = 0x0020, MOUSEEVENTF_MIDDLEUP = 0x0040;
  public const uint MOUSEEVENTF_WHEEL = 0x0800, MOUSEEVENTF_HWHEEL = 0x1000;
  public const uint KEYEVENTF_EXTENDEDKEY = 0x0001, KEYEVENTF_KEYUP = 0x0002, KEYEVENTF_UNICODE = 0x0004;

  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
  [StructLayout(LayoutKind.Sequential)] public struct MOUSEINPUT { public int dx; public int dy; public uint mouseData; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
  [StructLayout(LayoutKind.Sequential)] public struct KEYBDINPUT { public ushort wVk; public ushort wScan; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
  [StructLayout(LayoutKind.Sequential)] public struct HARDWAREINPUT { public uint uMsg; public ushort wParamL; public ushort wParamH; }
  [StructLayout(LayoutKind.Explicit)] public struct InputUnion { [FieldOffset(0)] public MOUSEINPUT mi; [FieldOffset(0)] public KEYBDINPUT ki; [FieldOffset(0)] public HARDWAREINPUT hi; }
  [StructLayout(LayoutKind.Sequential)] public struct INPUT { public uint type; public InputUnion U; }

  [DllImport("user32.dll", SetLastError = true)] static extern uint SendInput(uint n, INPUT[] inputs, int size);
  [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT point);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr window);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr window, int command);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr window);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr window, out RECT rect);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr window, StringBuilder text, int count);
  [DllImport("user32.dll")] public static extern int GetSystemMetrics(int index);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll", SetLastError = true)] public static extern uint GetWindowThreadProcessId(IntPtr window, out uint process);

  static INPUT Mouse(uint flags, int dx, int dy, uint data) {
    INPUT input = new INPUT(); input.type = INPUT_MOUSE;
    input.U.mi.dx = dx; input.U.mi.dy = dy; input.U.mi.mouseData = data; input.U.mi.dwFlags = flags;
    return input;
  }
  static INPUT Keyboard(uint flags, ushort vk, ushort scan) {
    INPUT input = new INPUT(); input.type = INPUT_KEYBOARD;
    input.U.ki.wVk = vk; input.U.ki.wScan = scan; input.U.ki.dwFlags = flags;
    return input;
  }
  public static uint SendMouse(uint flags, uint data) { return SendInput(1, new INPUT[] { Mouse(flags, 0, 0, data) }, Marshal.SizeOf(typeof(INPUT))); }
  public static uint SendMousePair(uint down, uint up, uint data) { return SendInput(2, new INPUT[] { Mouse(down, 0, 0, data), Mouse(up, 0, 0, data) }, Marshal.SizeOf(typeof(INPUT))); }
  public static uint SendKey(uint flags, ushort vk, ushort scan) { return SendInput(1, new INPUT[] { Keyboard(flags, vk, scan) }, Marshal.SizeOf(typeof(INPUT))); }
  public static uint SendKeyPair(uint flags, ushort vk, ushort scan) { return SendInput(2, new INPUT[] { Keyboard(flags, vk, scan), Keyboard(flags | KEYEVENTF_KEYUP, vk, scan) }, Marshal.SizeOf(typeof(INPUT))); }
  public static uint SendUnicode(char unit) {
    ushort scan = (ushort)unit;
    return SendInput(2, new INPUT[] { Keyboard(KEYEVENTF_UNICODE, 0, scan), Keyboard(KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, scan) }, Marshal.SizeOf(typeof(INPUT)));
  }
  public static string Title(IntPtr window) {
    int length = GetWindowText(window, null, 0);
    if (length <= 0) return "";
    StringBuilder text = new StringBuilder(length + 1);
    GetWindowText(window, text, text.Capacity);
    return text.ToString();
  }
}
'@
$script:dpiAware = [CCodeWin]::SetProcessDPIAware()

$script:failCode = 'helper'
$script:failHint = ''
function Fail([string]$message, [string]$code = 'helper', [string]$hint = '') {
  $script:failCode = $code
  $script:failHint = $hint
  throw $message
}

$script:extendedKeys = @(0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5C, 0x5D, 0x6F)
$script:namedKeys = @{
  'enter' = 13; 'return' = 13; 'tab' = 9; 'escape' = 27; 'esc' = 27; 'space' = 32; 'backspace' = 8;
  'delete' = 46; 'del' = 46; 'insert' = 45; 'ins' = 45; 'home' = 36; 'end' = 35;
  'pageup' = 33; 'pgup' = 33; 'pagedown' = 34; 'pgdn' = 34; 'up' = 38; 'down' = 40; 'left' = 37; 'right' = 39;
  'printscreen' = 44; 'prtsc' = 44; 'apps' = 93; 'menu' = 93; 'capslock' = 20; 'numlock' = 144;
  'plus' = 0xBB; 'add' = 0x6B; 'minus' = 0xBD; 'subtract' = 0x6D; 'comma' = 0xBC; 'period' = 0xBE;
  'slash' = 0xBF; 'backslash' = 0xDC; 'semicolon' = 0xBA; 'quote' = 0xDE; 'tilde' = 0xC0;
  'lbracket' = 0xDB; 'rbracket' = 0xDD; 'equals' = 0xBB
}
for ($index = 1; $index -le 24; $index++) { $script:namedKeys['f' + $index] = 0x6F + $index }

function Get-VirtualKey([string]$name) {
  $key = $name.ToLowerInvariant().Trim()
  if ($script:namedKeys.ContainsKey($key)) { return [int]$script:namedKeys[$key] }
  if ($key.Length -eq 1) {
    $code = [int][char]([char]::ToUpperInvariant($key[0]))
    if (($code -ge 48 -and $code -le 57) -or ($code -ge 65 -and $code -le 90)) { return $code }
  }
  Fail "Unknown key '$name'." 'key' 'Use names like Enter, Escape, Tab, F5, PageDown or a single character, joined with + for chords (Ctrl+L).'
}

function Get-ProcessName([int64]$window) {
  try {
    $process = 0
    [void][CCodeWin]::GetWindowThreadProcessId([IntPtr]$window, [ref]$process)
    if ($process -le 0) { return $null }
    return [System.Diagnostics.Process]::GetProcessById([int]$process).ProcessName
  } catch { return $null }
}

function Get-WindowTitle([int64]$window) {
  # UI Automation reports the title of packaged/WinUI windows that GetWindowText reports as
  # empty, so it is the primary source and the Win32 window text is the fallback.
  try {
    $element = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$window)
    if ($null -ne $element) {
      $name = [string]$element.Current.Name
      if (-not [string]::IsNullOrWhiteSpace($name)) { return $name.Trim() }
    }
  } catch { }
  return [CCodeWin]::Title([IntPtr]$window)
}

function Get-ForegroundInfo {
  $window = [CCodeWin]::GetForegroundWindow()
  $rect = New-Object 'CCodeWin+RECT'
  $hasRect = [CCodeWin]::GetWindowRect($window, [ref]$rect)
  return [ordered]@{
    hwnd = [int64]$window
    title = Get-WindowTitle ([int64]$window)
    process = Get-ProcessName ([int64]$window)
    rect = if ($hasRect) { [ordered]@{ x = $rect.Left; y = $rect.Top; width = $rect.Right - $rect.Left; height = $rect.Bottom - $rect.Top } } else { $null }
  }
}

function Get-TopLevelWindows {
  $root = [System.Windows.Automation.AutomationElement]::RootElement
  $condition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Window)
  $found = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $condition)
  $rows = New-Object System.Collections.ArrayList
  foreach ($node in $found) {
    if ($rows.Count -ge 200) { break }
    try {
      $rect = $node.Current.BoundingRectangle
      $handle = [int64]$node.Current.NativeWindowHandle
      [void]$rows.Add([ordered]@{
        hwnd = $handle
        title = [string]$node.Current.Name
        process = Get-ProcessName $handle
        pid = $node.Current.ProcessId
        x = [int][Math]::Round($rect.X); y = [int][Math]::Round($rect.Y)
        width = [int][Math]::Round($rect.Width); height = [int][Math]::Round($rect.Height)
      })
    } catch { continue }
  }
  return $rows
}

function Normalize-Text([string]$text, [int]$limit) {
  $flat = ($text -replace '\s+', ' ').Trim()
  if ($flat.Length -gt $limit) { $flat = $flat.Substring(0, $limit) + '...' }
  return $flat
}

# A control with no Name can still hold text: edit boxes expose a value, documents expose a
# text range. Without this fallback screen_read_text sees a window frame and nothing inside it.
function Get-NodeText($node, [int]$limit = 500) {
  try {
    $value = $node.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
    $text = [string]$value.Current.Value
    if (-not [string]::IsNullOrWhiteSpace($text)) { return Normalize-Text $text $limit }
  } catch { }
  try {
    $pattern = $node.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
    $text = [string]$pattern.DocumentRange.GetText($limit * 2)
    if (-not [string]::IsNullOrWhiteSpace($text)) { return Normalize-Text $text $limit }
  } catch { }
  return ''
}

# ControlViewWalker with an explicit budget: FindAll on a busy window can return thousands of
# nodes, and the model only needs the labelled ones it can click.
function Get-Elements($root, [int]$limit) {
  $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
  $stack = New-Object System.Collections.Stack
  $stack.Push($root)
  $rows = New-Object System.Collections.ArrayList
  $visited = 0
  $isOffscreen = [System.Windows.Automation.AutomationElement]::IsOffscreenProperty
  while ($stack.Count -gt 0 -and $rows.Count -lt $limit -and $visited -lt ($limit * 6)) {
    $node = $stack.Pop()
    $visited++
    try {
      $child = $walker.GetFirstChild($node)
      while ($null -ne $child) { $stack.Push($child); $child = $walker.GetNextSibling($child) }
    } catch { }
    try {
      $current = $node.Current
      if ($current.IsOffscreen) { continue }
      $rect = $current.BoundingRectangle
      if ($rect.Width -lt 2 -or $rect.Height -lt 2) { continue }
      $text = [string]$current.Name
      $type = [string]$current.ControlType.ProgrammaticName
      if ($type -eq 'ControlType.Document' -or $type -eq 'ControlType.Edit') {
        # An editor's Name is a label ("Text editor"); its content is what the model needs.
        $content = Get-NodeText $node 500
        if (-not [string]::IsNullOrWhiteSpace($content)) { $text = $content }
      } elseif ([string]::IsNullOrWhiteSpace($text) -and $current.IsContentElement) {
        $text = Get-NodeText $node 500
      }
      if ([string]::IsNullOrWhiteSpace($text)) { continue }
      $role = [string]$current.LocalizedControlType
      if ([string]::IsNullOrWhiteSpace($role)) { $role = ([string]$current.ControlType.ProgrammaticName) -replace '^ControlType\.', '' }
      [void]$rows.Add([ordered]@{
        role = $role
        text = Normalize-Text $text 500
        x = [int][Math]::Round($rect.X + $rect.Width / 2)
        y = [int][Math]::Round($rect.Y + $rect.Height / 2)
        left = [int][Math]::Round($rect.X); top = [int][Math]::Round($rect.Y)
        width = [int][Math]::Round($rect.Width); height = [int][Math]::Round($rect.Height)
        enabled = [bool]$current.IsEnabled
      })
    } catch { continue }
  }
  return $rows
}

function Get-Desktop {
  $screens = New-Object System.Collections.ArrayList
  foreach ($screen in [System.Windows.Forms.Screen]::AllScreens) {
    [void]$screens.Add([ordered]@{
      name = $screen.DeviceName; primary = $screen.Primary
      x = $screen.Bounds.X; y = $screen.Bounds.Y; width = $screen.Bounds.Width; height = $screen.Bounds.Height
    })
  }
  $virtual = [System.Windows.Forms.SystemInformation]::VirtualScreen
  # Coordinates are physical pixels because the process declared system DPI awareness at
  # startup; per-monitor DPI on mixed setups still has to be verified on the machine.
  return [ordered]@{
    x = $virtual.X; y = $virtual.Y; width = $virtual.Width; height = $virtual.Height; monitors = $screens
    dpi_aware = $script:dpiAware
  }
}

function Invoke-Screenshot($payload) {
  $x = [int]$payload.x; $y = [int]$payload.y; $width = [int]$payload.width; $height = [int]$payload.height
  if ($width -lt 1 -or $height -lt 1) { Fail 'The screenshot region is empty.' 'region' }
  $targetWidth = [int]$payload.targetWidth; $targetHeight = [int]$payload.targetHeight
  $source = New-Object System.Drawing.Bitmap($width, $height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $scaled = $null
  $graphics = $null
  $scaledGraphics = $null
  try {
    $graphics = [System.Drawing.Graphics]::FromImage($source)
    $graphics.CopyFromScreen($x, $y, 0, 0, (New-Object System.Drawing.Size($width, $height)), [System.Drawing.CopyPixelOperation]::SourceCopy)
    $canvas = $source
    if ($targetWidth -ne $width -or $targetHeight -ne $height) {
      $scaled = New-Object System.Drawing.Bitmap($targetWidth, $targetHeight)
      $scaledGraphics = [System.Drawing.Graphics]::FromImage($scaled)
      $scaledGraphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
      $scaledGraphics.DrawImage($source, 0, 0, $targetWidth, $targetHeight)
      $canvas = $scaled
    }
    if ($payload.marks) {
      $markGraphics = [System.Drawing.Graphics]::FromImage($canvas)
      try {
        $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(255, 255, 0, 0), 2)
        $brush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(220, 255, 255, 0))
        $textBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 0, 0, 0))
        $font = New-Object System.Drawing.Font('Arial', 10, [System.Drawing.FontStyle]::Bold)
        $scale = $targetWidth / $width
        try {
          foreach ($mark in $payload.marks) {
            $mx = [int]($mark.x * $scale); $my = [int]($mark.y * $scale)
            $mw = [Math]::Max(2, [int]($mark.width * $scale)); $mh = [Math]::Max(2, [int]($mark.height * $scale))
            $markGraphics.DrawRectangle($pen, $mx, $my, $mw, $mh)
            $label = [string]$mark.label
            $size = $markGraphics.MeasureString($label, $font)
            $markGraphics.FillRectangle($brush, $mx, $my, $size.Width, $size.Height)
            $markGraphics.DrawString($label, $font, $textBrush, $mx, $my)
          }
        } finally {
          $pen.Dispose(); $brush.Dispose(); $textBrush.Dispose(); $font.Dispose()
        }
      } finally { $markGraphics.Dispose() }
    }
    $stream = New-Object System.IO.MemoryStream
    try {
      $canvas.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
      $bytes = $stream.ToArray()
    } finally { $stream.Dispose() }
    $digest = [System.Security.Cryptography.SHA256]::Create()
    try {
      $hash = [System.BitConverter]::ToString($digest.ComputeHash($bytes)).Replace('-', '').ToLowerInvariant()
    } finally { $digest.Dispose() }
    $data = [ordered]@{ bytes = $bytes.Length; width = $targetWidth; height = $targetHeight; sha256 = $hash }
    if ($null -eq $payload.encode -or $payload.encode -ne $false) { $data['png'] = [System.Convert]::ToBase64String($bytes) }
    return $data
  } finally {
    if ($scaledGraphics) { $scaledGraphics.Dispose() }
    if ($graphics) { $graphics.Dispose() }
    if ($scaled) { $scaled.Dispose() }
    $source.Dispose()
  }
}

function Assert-Input([uint32]$sent, [int]$expected, [string]$action) {
  if ($sent -eq $expected) { return }
  $error = [System.Runtime.InteropServices.Marshal]::GetLastWin32Error()
  Fail "Windows refused the $action input (SendInput sent $sent of $expected events, Win32 error $error). The target window is probably elevated: UIPI blocks input from this non-elevated process." 'uipi' 'Elevated windows (Task Manager, regedit, an elevated console) and the UAC secure desktop cannot be driven from a normal process. There is no force flag that pierces elevation. Ask the user to do that step, or automate a non-elevated target.'
}

function Invoke-Click($payload) {
  $button = if ($payload.button) { ([string]$payload.button).ToLowerInvariant() } else { 'left' }
  $down = switch ($button) { 'right' { [CCodeWin]::MOUSEEVENTF_RIGHTDOWN } 'middle' { [CCodeWin]::MOUSEEVENTF_MIDDLEDOWN } 'left' { [CCodeWin]::MOUSEEVENTF_LEFTDOWN } default { Fail "Unknown button '$button'." 'button' 'Use left, right, or middle.' } }
  $up = switch ($button) { 'right' { [CCodeWin]::MOUSEEVENTF_RIGHTUP } 'middle' { [CCodeWin]::MOUSEEVENTF_MIDDLEUP } 'left' { [CCodeWin]::MOUSEEVENTF_LEFTUP } }
  if ($null -ne $payload.x -and $null -ne $payload.y) {
    if (-not [CCodeWin]::SetCursorPos([int]$payload.x, [int]$payload.y)) { Fail 'Could not move the pointer to the target point.' 'pointer' }
    Start-Sleep -Milliseconds 30
  }
  $clicks = if ($payload.double) { 2 } else { 1 }
  for ($index = 0; $index -lt $clicks; $index++) {
    Assert-Input ([CCodeWin]::SendMousePair($down, $up, 0)) 2 'mouse click'
    if ($index -lt $clicks - 1) { Start-Sleep -Milliseconds 60 }
  }
  $point = New-Object CCodeWin+POINT
  [void][CCodeWin]::GetCursorPos([ref]$point)
  return [ordered]@{ clicked = $button; count = $clicks; x = $point.X; y = $point.Y }
}

function Invoke-Type($payload) {
  $text = [string]$payload.text
  if ([string]::IsNullOrEmpty($text)) { Fail 'text is required.' 'args' }
  $units = $text.ToCharArray()
  $typed = 0
  for ($index = 0; $index -lt $units.Length; $index++) {
    $unit = $units[$index]
    if ($unit -eq "`r" -and $index + 1 -lt $units.Length -and $units[$index + 1] -eq "`n") { continue }
    if ($unit -eq "`n" -or $unit -eq "`r") { Assert-Input ([CCodeWin]::SendKeyPair(0, 13, 0)) 2 'keyboard'; $typed++ }
    elseif ($unit -eq "`t") { Assert-Input ([CCodeWin]::SendKeyPair(0, 9, 0)) 2 'keyboard'; $typed++ }
    else { Assert-Input ([CCodeWin]::SendUnicode($unit)) 2 'keyboard'; $typed++ }
  }
  return [ordered]@{ typed = $typed; characters = $text.Length }
}

function Invoke-Key($payload) {
  $keys = [string]$payload.keys
  if ([string]::IsNullOrWhiteSpace($keys)) { Fail 'keys is required (e.g. Ctrl+L).' 'args' }
  $parts = $keys.Split('+') | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' }
  if ($parts.Count -eq 0) { Fail 'keys is required (e.g. Ctrl+L).' 'args' }
  $modifiers = New-Object System.Collections.ArrayList
  $base = $null
  foreach ($part in $parts) {
    switch ($part.ToLowerInvariant()) {
      'ctrl' { [void]$modifiers.Add(0x11) }
      'control' { [void]$modifiers.Add(0x11) }
      'shift' { [void]$modifiers.Add(0x10) }
      'alt' { [void]$modifiers.Add(0x12) }
      'win' { [void]$modifiers.Add(0x5B) }
      'meta' { [void]$modifiers.Add(0x5B) }
      default { $base = $part }
    }
  }
  if ($null -eq $base) { Fail "keys needs a base key, got '$keys'." 'args' }
  $vk = Get-VirtualKey $base
  $flags = if ($script:extendedKeys -contains $vk) { [CCodeWin]::KEYEVENTF_EXTENDEDKEY } else { 0 }
  $held = New-Object System.Collections.ArrayList
  try {
    foreach ($modifier in $modifiers) {
      Assert-Input ([CCodeWin]::SendKey(0, [uint16]$modifier, 0)) 1 'keyboard'
      [void]$held.Add($modifier)
    }
    Assert-Input ([CCodeWin]::SendKeyPair($flags, [uint16]$vk, 0)) 2 'keyboard'
  } finally {
    for ($index = $held.Count - 1; $index -ge 0; $index--) { [void][CCodeWin]::SendKey([CCodeWin]::KEYEVENTF_KEYUP, [uint16]$held[$index], 0) }
  }
  return [ordered]@{ keys = $keys; virtual_key = $vk }
}

function Invoke-Scroll($payload) {
  $direction = if ($payload.direction) { ([string]$payload.direction).ToLowerInvariant() } else { 'down' }
  $amount = if ($payload.amount) { [int]$payload.amount } else { 3 }
  if ($amount -lt 1 -or $amount -gt 50) { Fail 'amount must be between 1 and 50.' 'args' }
  if ($null -ne $payload.x -and $null -ne $payload.y) {
    if (-not [CCodeWin]::SetCursorPos([int]$payload.x, [int]$payload.y)) { Fail 'Could not place the pointer over the scroll target.' 'pointer' }
    Start-Sleep -Milliseconds 30
  }
  $delta = 120 * $amount
  switch ($direction) {
    'up' { $flag = [CCodeWin]::MOUSEEVENTF_WHEEL; $signed = $delta }
    'down' { $flag = [CCodeWin]::MOUSEEVENTF_WHEEL; $signed = -$delta }
    'right' { $flag = [CCodeWin]::MOUSEEVENTF_HWHEEL; $signed = $delta }
    'left' { $flag = [CCodeWin]::MOUSEEVENTF_HWHEEL; $signed = -$delta }
    default { Fail "Unknown direction '$direction'." 'args' 'Use up, down, left, or right.' }
  }
  # mouseData is unsigned but a negative wheel delta is the documented encoding.
  $data = if ($signed -lt 0) { $signed + 4294967296 } else { $signed }
  $sent = 0
  for ($index = 0; $index -lt $amount; $index++) {
    Assert-Input ([CCodeWin]::SendMouse($flag, [uint32]$data)) 1 'scroll'
    $sent++
    Start-Sleep -Milliseconds 20
  }
  return [ordered]@{ direction = $direction; steps = $sent }
}

function Invoke-Focus($payload) {
  $windows = Get-TopLevelWindows
  $wanted = [string]$payload.window
  $app = if ($payload.app) { ([string]$payload.app).ToLowerInvariant() } else { $null }
  $title = if ($payload.title) { ([string]$payload.title).ToLowerInvariant() } else { $null }
  if (-not $wanted -and -not $app -and -not $title) { Fail 'screen_focus needs app, title, or window.' 'args' 'Example: screen_focus(app="notepad").' }
  $matches = New-Object System.Collections.ArrayList
  foreach ($row in $windows) {
    if ($wanted -and ([string]$row.hwnd) -eq $wanted) { [void]$matches.Add($row); continue }
    $name = ([string]$row.title).ToLowerInvariant()
    $process = ([string]$row.process).ToLowerInvariant()
    if ($app -and ($name.Contains($app) -or $process.Contains($app))) { [void]$matches.Add($row); continue }
    if ($title -and $name.Contains($title)) { [void]$matches.Add($row) }
  }
  if ($matches.Count -eq 0) {
    $sample = ($windows | Select-Object -First 12 | ForEach-Object { "'" + $_.title + "' (hwnd " + $_.hwnd + ", pid " + $_.process + ")" }) -join '; '
    Fail 'No window matched the focus request.' 'focus-not-found' ('Windows visible to UI Automation: ' + $sample + '. Pass the exact hwnd with window=<id>.')
  }
  if ($matches.Count -gt 1 -and -not $wanted) {
    $sample = ($matches | Select-Object -First 12 | ForEach-Object { "'" + $_.title + "' (hwnd " + $_.hwnd + ")" }) -join '; '
    Fail 'More than one window matched; pass a narrower title or the exact window=<hwnd>.' 'focus-ambiguous' ('Candidates: ' + $sample)
  }
  $target = $matches[0]
  $window = [IntPtr][int64]$target.hwnd
  if ([CCodeWin]::IsIconic($window)) { [void][CCodeWin]::ShowWindow($window, 9) }
  [void][CCodeWin]::SetForegroundWindow($window)
  Start-Sleep -Milliseconds 120
  $foreground = [CCodeWin]::GetForegroundWindow()
  if ($foreground -ne $window) {
    Fail ('Focus did not transfer to ' + $target.title + ' (hwnd ' + $target.hwnd + '); the foreground window is still hwnd ' + [int64]$foreground + '.') 'focus-refused' 'Windows only lets a process raise its own window unless the foreground lock is free: use focus only when the user is not typing elsewhere, and note that an elevated window can never be raised from here (UIPI).'
  }
  return [ordered]@{ hwnd = $target.hwnd; title = $target.title; process = $target.process; focused = $true }
}

function Invoke-Op([string]$op, $payload) {
  switch ($op) {
    'ping' { return [ordered]@{ pid = $PID; ps = $PSVersionTable.PSVersion.ToString(); dpi_aware = $true } }
    'cursor' {
      $point = New-Object CCodeWin+POINT
      if (-not [CCodeWin]::GetCursorPos([ref]$point)) { Fail 'Could not read the pointer position.' 'pointer' }
      return [ordered]@{ x = $point.X; y = $point.Y }
    }
    'desktop' { return Get-Desktop }
    'foreground' {
      $info = Get-ForegroundInfo
      $info['topLevel'] = @(Get-TopLevelWindows).Count
      return $info
    }
    'elements' {
      $limit = if ($payload.limit) { [int]$payload.limit } else { 400 }
      $root = if ($payload.root -eq 'desktop') { [System.Windows.Automation.AutomationElement]::RootElement } else {
        $window = [CCodeWin]::GetForegroundWindow()
        [System.Windows.Automation.AutomationElement]::FromHandle($window)
      }
      if ($null -eq $root) { Fail 'The foreground window could not be read through UI Automation.' 'uia' }
      $rows = Get-Elements $root $limit
      $contains = if ($payload.contains) { ([string]$payload.contains).ToLowerInvariant() } else { $null }
      if ($contains) { $rows = @($rows | Where-Object { ([string]$_.text).ToLowerInvariant().Contains($contains) }) }
      $info = Get-ForegroundInfo
      return [ordered]@{ focused = $info; rect = $info.rect; count = @($rows).Count; elements = @($rows) }
    }
    'focus' { return Invoke-Focus $payload }
    'screenshot' {
      $data = Invoke-Screenshot $payload
      # The observation carries its own geometry so one round trip answers "what changed and
      # where am I": the pixels, the desktop, the focused window, and the top-level window count.
      $data['virtual'] = Get-Desktop
      $data['foreground'] = Get-ForegroundInfo
      $data['topLevel'] = @(Get-TopLevelWindows).Count
      return $data
    }
    'click' { return Invoke-Click $payload }
    'type' { return Invoke-Type $payload }
    'key' { return Invoke-Key $payload }
    'scroll' { return Invoke-Scroll $payload }
    default { Fail "Unknown helper operation '$op'." 'op' }
  }
}

while ($true) {
  $line = [Console]::In.ReadLine()
  if ($null -eq $line) { break }
  if ($line.Trim().Length -eq 0) { continue }
  $id = $null
  $reply = $null
  $script:failCode = 'helper'
  $script:failHint = ''
  try {
    $request = $line | ConvertFrom-Json
    $id = $request.id
    $reply = @{ id = $id; ok = $true; data = (Invoke-Op ([string]$request.op) $request.args) }
  } catch {
    $reply = @{ id = $id; ok = $false; error = $_.Exception.Message; code = $script:failCode; hint = $script:failHint }
  }
  [Console]::Out.WriteLine(($reply | ConvertTo-Json -Compress -Depth 8))
  [Console]::Out.Flush()
}
