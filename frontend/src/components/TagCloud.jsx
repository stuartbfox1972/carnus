import React, { useMemo } from 'react';

const TagCloud = ({ tags, searchQuery, onSearchChange, onTagClick }) => {
  if (!tags || tags.length === 0) return null;

  // 1. Strictly lock Top 5 by Count for the blue pill bar
  const topFive = useMemo(() => {
    return [...tags].sort((a, b) => b.Count - a.Count).slice(0, 5);
  }, [tags]);

  // 2. The Cloud: Random shuffle for that organic interlocking feel
  const theCloud = useMemo(() => {
    const topFiveIds = new Set(topFive.map(t => t.SK));
    return tags
      .filter(t => !topFiveIds.has(t.SK) && t.LabelName.toLowerCase().includes(searchQuery.toLowerCase()))
      .sort(() => Math.random() - 0.5);
  }, [tags, searchQuery, topFive]);

  const counts = theCloud.map(t => t.Count);
  const max = Math.max(...counts, 1);
  const min = Math.min(...counts, 1);

  const colors = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#64748b'];
  const fontStack = "'Inter', 'Segoe UI', Roboto, sans-serif";

  return (
    <div style={{ 
      textAlign: 'center', 
      padding: '40px 0', 
      width: '100vw', 
      marginLeft: '50%',
      transform: 'translateX(-50%)',
      fontFamily: fontStack,
      color: '#1e293b'
    }}>
      <h2 style={{ fontSize: '2.5rem', fontWeight: '800', marginBottom: '10px', letterSpacing: '-0.05em' }}>
        Discovery Cloud
      </h2>
      
      <div style={{ marginBottom: '60px' }}>
        <input 
          type="text" 
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Filter keywords..." 
          style={{ 
            width: '100%', maxWidth: '400px', padding: '14px 24px', borderRadius: '30px', 
            border: '1px solid #e2e8f0', fontSize: '16px', outline: 'none', background: '#f8fafc'
          }}
        />
      </div>

      {/* TOP 5: Blue Pills */}
      <div style={{ display: 'flex', justifyContent: 'center', gap: '10px', flexWrap: 'wrap', marginBottom: '80px' }}>
        {topFive.map(t => (
          <button 
            key={t.SK} 
            onClick={() => onTagClick(t.LabelName)} 
            className="status-pill" 
            style={{ cursor: 'pointer', border: 'none', padding: '10px 24px', fontWeight: '600' }}
          >
            {t.LabelName} ({t.Count})
          </button>
        ))}
      </div>

      {/* THE DENSE CLOUD: No Zooming, No Blocking */}
      <div style={{ 
        width: '80vw', 
        margin: '0 auto',
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'center',
        alignItems: 'baseline',
        gap: '2px 15px', // Tight gap for the interlocking look
        paddingBottom: '100px'
      }}>
        {theCloud.map((t, idx) => {
          // Dynamic scale: 12px to 75px
          const size = min === max ? 20 : 12 + ((t.Count - min) / (max - min)) * 63;
          const color = colors[idx % colors.length];

          return (
            <span
              key={t.SK}
              onClick={() => onTagClick(t.LabelName)}
              style={{
                fontSize: `${size}px`,
                fontWeight: '400',
                color: color,
                cursor: 'pointer',
                transition: 'color 0.2s ease, opacity 0.2s ease', // Only color/opacity change
                opacity: size > 30 ? 1 : 0.6,
                display: 'inline-block',
                padding: '0 2px',
                lineHeight: '0.8', // Negative space forces nesting
                letterSpacing: '-0.04em',
                whiteSpace: 'nowrap'
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.color = '#2563eb'; // Sharp blue on hover
                e.currentTarget.style.opacity = '1';
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.color = color;
                e.currentTarget.style.opacity = size > 30 ? '1' : '0.6';
              }}
            >
              {t.LabelName}
            </span>
          );
        })}
      </div>
    </div>
  );
};

export default TagCloud;
