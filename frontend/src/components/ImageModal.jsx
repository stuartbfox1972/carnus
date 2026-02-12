import React from 'react';

const ImageModal = ({ image, onClose, onTagClick }) => {
  if (!image) return null;

  const hardwareKeys = ['Make', 'CameraModel', 'Lens', 'Aperture', 'ShutterSpeed', 'ISO', 'FocalLength'];
  const blacklist = ['Labels', 'Faces', 'DetailUrl', 'ThumbnailUrl', 'ImageId', 'ThumbnailKey', 'PK', 'SK', 'ProcessedAt', 'ImageName', 'Tag'];

  // Sort entries so hardware info appears first
  const sortedEntries = Object.entries(image)
    .filter(([k]) => !blacklist.includes(k))
    .sort((a, b) => {
      const aIndex = hardwareKeys.indexOf(a[0]);
      const bIndex = hardwareKeys.indexOf(b[0]);
      if (aIndex !== -1 && bIndex !== -1) return aIndex - bIndex;
      if (aIndex !== -1) return -1;
      if (bIndex !== -1) return 1;
      return a[0].localeCompare(b[0]);
    });

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div 
        style={{ 
          background: 'white', 
          borderRadius: '12px', 
          maxWidth: '900px', 
          width: '95%', 
          maxHeight: '95vh', 
          overflow: 'hidden', 
          position: 'relative',
          display: 'flex',
          flexDirection: 'column'
        }} 
        onClick={e => e.stopPropagation()}
      >
        {/* Header Area: Image and Face Boxes */}
        <div style={{ padding: '20px', background: '#0f172a', textAlign: 'center', flexShrink: 0 }}>
          <div style={{ position: 'relative', display: 'inline-block' }}>
            <img 
              src={image.DetailUrl || image.ThumbnailUrl} 
              style={{ maxHeight: '50vh', maxWidth: '100%', borderRadius: '4px' }} 
              alt={image.ImageName} 
            />
            {/* Face Bounding Boxes */}
            {image.Faces?.map((f, i) => (
              <div key={i} style={{
                position: 'absolute', 
                border: '2px solid #3b82f6', 
                background: 'rgba(59, 130, 246, 0.2)',
                left: `${f.BoundingBox.Left * 100}%`, 
                top: `${f.BoundingBox.Top * 100}%`,
                width: `${f.BoundingBox.Width * 100}%`, 
                height: `${f.BoundingBox.Height * 100}%`, 
                pointerEvents: 'none'
              }} />
            ))}
          </div>

          {/* AI Labels Pivot Bar */}
          <div style={{ marginTop: '15px', display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: '8px' }}>
            {image.Labels?.map(l => (
              <button 
                key={l} 
                className="status-pill" 
                onClick={() => onTagClick(l)}
              >
                {l}
              </button>
            ))}
          </div>
        </div>

        {/* Data Area: Hardware and EXIF */}
        <div style={{ padding: '25px', overflowY: 'auto', flexGrow: 1 }}>
          <h4 style={{ marginTop: 0, marginBottom: '15px', color: '#64748b', fontSize: '12px', textTransform: 'uppercase' }}>
            Image Metadata - {image.ImageName}
          </h4>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', background: '#e2e8f0', gap: '1px', border: '1px solid #e2e8f0' }}>
            {sortedEntries.map(([k, v]) => (
              <React.Fragment key={k}>
                <div style={{ background: '#f8fafc', padding: '12px', fontSize: '11px', fontWeight: 'bold', color: '#475569' }}>
                  {k}
                </div>
                <div style={{ background: 'white', padding: '12px', fontSize: '13px', color: '#1e293b' }}>
                  {hardwareKeys.includes(k) ? (
                    <span 
                      className="pivot-link" 
                      onClick={() => onTagClick(String(v))}
                    >
                      {String(v)}
                    </span>
                  ) : (
                    String(v)
                  )}
                </div>
              </React.Fragment>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ImageModal;
