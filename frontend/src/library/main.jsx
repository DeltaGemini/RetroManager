// Notifications, the modal every panel uses, and starting the app.
// Part of the library page (index.html), which loads these files in order;
// they share one global scope, so each can use what the ones before it define.

function Notification({ message, type }) {
    return <div className={`notification ${type}`}>{message}</div>;
}

// Drawn on document.body so no panel's stacking order can cover it
function Modal({ open, onClose, children }) {
    if (!open) return null;
    return ReactDOM.createPortal(
<div style={{
    position: 'fixed',
    top: 0,
    left: 0,
    width: '100vw',
    height: '100vh',
    background: 'rgba(0,0,0,0.7)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000
}} {...backdropClose(onClose)}>
    <div style={{
        background: 'var(--bg-modal)',
        padding: 24,
        borderRadius: 8,
        maxHeight: '95vh',
        minWidth: '65%',
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
        position: 'relative',
        overflowY: 'auto'
    }} onClick={e => e.stopPropagation()}>
        <button style={{
            position: 'absolute',
            top: 12,
            right: 12,
            background: 'var(--accent-pink)',
            color: 'white',
            border: 'none',
            borderRadius: 4,
            padding: '6px 12px',
            cursor: 'pointer',
            fontWeight: 600
        }} onClick={onClose}>Close</button>
        {children}
    </div>
</div>,
document.body
    );
}

// React 18 compatible rendering
const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
