import React from 'react';

const GalleryGrid = ({ images, selectedTag, onImageClick, onBack, nextKey, onLoadMore }) => {
  const displayImages = Array.isArray(images) ? images : (images?.items || []);

  return (
    <section>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '30px' }}>
        <h3 style={{ margin: 0 }}>
          Results for: <span style={{ color: '#3b82f6' }}>{selectedTag.replace('TAG#', '')}</span>
        </h3>
        <button 
          onClick={onBack} 
          style={{ cursor: 'pointer', padding: '8px 20px', borderRadius: '20px', border: 'none', background: '#232f3e', color: 'white', fontWeight: 'bold' }}
        >
          ← Back
        </button>
      </div>

      {/* THE GRID LAYOUT */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', 
        gap: '20px',
        width: '100%' 
      }}>
        {displayImages.map((img) => (
          <div 
            key={img.ImageId} 
            onClick={() => onImageClick(img)}
            style={{ 
              background: 'white', 
              borderRadius: '8px', 
              overflow: 'hidden', 
              border: '1px solid #e2e8f0', 
              cursor: 'pointer',
              transition: 'transform 0.1s ease'
            }}
            onMouseOver={(e) => e.currentTarget.style.transform = 'scale(1.02)'}
            onMouseOut={(e) => e.currentTarget.style.transform = 'scale(1)'}
          >
            <div style={{ width: '100%', height: '200px', overflow: 'hidden', background: '#f1f5f9' }}>
              <img 
                src={img.ThumbnailUrl} 
                alt="" 
                style={{ width: '100%', height: '100%', objectFit: 'cover' }} 
              />
            </div>
            <div style={{ padding: '10px', fontSize: '11px', textAlign: 'center', fontWeight: '500', color: '#475569', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {img.ImageName}
            </div>
          </div>
        ))}
      </div>

      {nextKey && (
        <div style={{ textAlign: 'center', marginTop: '40px' }}>
          <button onClick={onLoadMore} style={{ padding: '12px 24px', cursor: 'pointer', borderRadius: '30px', border: '2px solid #3b82f6', background: 'transparent', color: '#3b82f6', fontWeight: 'bold' }}>
            Load More
          </button>
        </div>
      )}
    </section>
  );
};

export default GalleryGrid;
