# Jeeves Development Roadmap

## Stats Page Enhancements

### Activity Heatmap
- **Goal**: Visualize channel activity patterns over time
- **Features**:
  - Heatmap showing message activity by hour of day and day of week
  - Color gradient to indicate activity levels (low to high)
  - Separate heatmaps per channel or combined view
  - Data aggregation from message logs/stats

### Extended Statistics
- **User Activity Stats**:
  - Most active users by message count
  - Most active times per user
  - User participation trends over time

- **Channel Analytics**:
  - Peak activity hours for each channel
  - Day-of-week activity patterns
  - Message count trends (daily/weekly/monthly)

- **Module Usage Stats**:
  - Most-used commands
  - Popular modules by invocation count
  - Command usage trends over time

### Achievements Integration
- **Achievements Page** (In Progress):
  - Display all available achievements
  - Show unlocked vs locked achievements
  - Track first-to-unlock for each achievement
  - User-specific achievement progress
  - Global achievement leaderboard

### Technical Implementation Notes
- Consider using Chart.js or similar for visualizations
- May need to add message tracking/logging if not already present
- Heatmap could use HTML/CSS grid with color gradients
- Cache computed stats to avoid performance issues
- Paginate or filter large datasets

## Future Ideas
- User timezone-aware activity tracking
- Comparative stats between users
- Achievement categories and filtering
- Achievement notifications in other channels (opt-in)
