# GUI Styling Updates - ODMR Style Integration

This document outlines the styling changes made to the Confocal Microscopy Control Center to match the professional appearance of the ODMR Control Center GUI.

## 🎨 Color Scheme

### Primary Colors
- **Background**: `#262930` (Dark blue-grey)
- **Text**: `#ffffff` (White)
- **Accent**: `#00d4aa` (Teal/Green)
- **Hover**: `#00ffcc` (Light teal)
- **Pressed**: `#009980` (Dark teal)

### Secondary Colors
- **Input Fields**: `#3c3c3c` (Dark grey)
- **Disabled**: `#555555` (Medium grey)
- **Border**: `#555555` (Medium grey)
- **Terminal Text**: `#00ff00` (Green - for status messages)
- **Plot Colors**: `#00ff88` (Green for curves), `#00d4aa` (Symbol highlights)

## 🖼️ Visual Components Updated

### Main Window
- **Background**: Dark theme throughout
- **Title**: "NV Scanning Microscopy Control Center - Burke Lab"
- **Spacing**: Professional margins and spacing (15px between panels, 10px internal spacing)
- **Width**: Left panel increased to 320px for better component fit

### Buttons
- **Style**: Rounded corners (4px), bold text
- **Colors**: Teal background with hover/press effects
- **Disabled State**: Grey with reduced opacity
- **Size**: Consistent 8px padding

### Group Boxes
- **Border**: 2px solid grey with rounded corners (8px)
- **Title**: Teal color with proper positioning
- **Padding**: 10px top margin for title spacing

### Input Fields
- **Background**: Dark grey (`#3c3c3c`)
- **Focus**: Teal border highlight
- **Text**: White on dark background
- **Consistency**: All spinboxes, line edits, combo boxes styled uniformly

### Progress Bars
- **Background**: Dark grey
- **Fill**: Teal color matching accent scheme
- **Text**: White centered text

### Tabs
- **Inactive**: Dark grey background
- **Active**: Teal background with bold text
- **Hover**: Medium grey for better UX

## 📊 Plot Styling

### PyQtGraph Plots
- **Background**: `#262930` (matching main theme)
- **Grid**: White with 30% opacity
- **Axes**: White lines and text
- **Curves**: `#00ff88` (green) with 2px width
- **Symbols**: Teal fill (`#00d4aa`) with green outline
- **Labels**: White text, 12pt size

### Image Display
- **Background**: Dark theme
- **Colormap**: Viridis (matching ODMR GUI scientific visualization)
- **Axes**: White labels and tick marks

### Specialized Plots
- **Live Signal**: Green curve with dark background
- **Auto-Focus**: Green curve with teal symbol highlights
- **Single Axis**: Green curve with symbol markers
- **Best Position Highlights**: Large teal symbols with light teal outline

## 🔧 Technical Implementation

### Main Stylesheet
Applied comprehensive `setStyleSheet()` covering:
- All widget types (QMainWindow, QWidget, QPushButton, etc.)
- Hover and focus states
- Disabled states
- Layout components (splitters, scrollbars)

### PyQtGraph Theming
- Background colors set via `setBackground()`
- Axis styling via `setPen()` and `setTextPen()`
- Plot colors via `pg.mkPen()` with specific colors
- Symbol styling with brush and pen colors

### Layout Improvements
- Consistent margins: 5-15px depending on component
- Professional spacing between elements
- Proper widget sizing (320px left panel, 200-250px plot heights)

## 🎯 Professional Features

### Status Messaging
- **Status Bar**: Terminal-style green text on dark background
- **Font**: Monospace (Consolas/Monaco) for technical appearance
- **Messages**: 3-second timeout with console logging

### Application Identity
- **Name**: "NV Scanning Microscopy Control Center"
- **Organization**: "Burke Lab - UC Irvine"
- **Domain**: "burkelab.uci.edu"
- **Version**: "2.0" (clean versioning)

### Consistency with ODMR GUI
- Identical color values and styling approach
- Same component styling (buttons, inputs, groups)
- Matching plot themes and scientific visualization
- Professional spacing and layout organization

## 🔍 Before/After Comparison

### Before (Napari/Basic PyQt)
- Default system styling
- Inconsistent colors and spacing
- Basic matplotlib plots
- No cohesive theme

### After (ODMR Style)
- Professional dark theme throughout
- Consistent teal accent colors
- High-contrast scientific visualization
- Cohesive laboratory software appearance

## 🚀 User Experience Improvements

### Visual Hierarchy
- Clear distinction between controls and display areas
- Consistent button styling for actions
- Group boxes clearly organize related parameters

### Accessibility
- High contrast white text on dark backgrounds
- Clear focus indicators with teal highlights
- Consistent sizing and spacing for easy navigation

### Professional Appearance
- Scientific software aesthetic
- Laboratory equipment-style dark theme
- Consistent with other Burke Lab software tools

---

**Result**: The Confocal Microscopy Control Center now has a unified, professional appearance that matches the ODMR Control Center, creating a cohesive software suite for the Burke Lab NV center experiments. 