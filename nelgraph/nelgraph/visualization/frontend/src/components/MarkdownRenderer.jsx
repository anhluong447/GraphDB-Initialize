import React from 'react';

export default function MarkdownRenderer({ content }) {
  if (!content) return null;

  const lines = content.split('\n');
  const renderedElements = [];
  
  let inCodeBlock = false;
  let codeLines = [];
  let codeLang = '';
  
  let inTable = false;
  let tableHeaders = [];
  let tableRows = [];
  
  let inList = false;
  let listItems = [];

  const flushList = (key) => {
    if (listItems.length > 0) {
      renderedElements.push(
        <ul key={`list-${key}`} style={styles.ul}>
          {listItems.map((item, idx) => (
            <li key={idx} style={styles.li}>{item}</li>
          ))}
        </ul>
      );
      listItems = [];
      inList = false;
    }
  };

  const flushTable = (key) => {
    if (tableHeaders.length > 0 || tableRows.length > 0) {
      renderedElements.push(
        <div key={`table-wrapper-${key}`} style={styles.tableWrapper}>
          <table style={styles.table}>
            {tableHeaders.length > 0 && (
              <thead>
                <tr>
                  {tableHeaders.map((h, idx) => (
                    <th key={idx} style={styles.th}>{h}</th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody>
              {tableRows.map((row, idx) => (
                <tr key={idx} style={idx % 2 === 0 ? styles.trEven : styles.trOdd}>
                  {row.map((cell, cIdx) => (
                    <td key={cIdx} style={styles.td}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      tableHeaders = [];
      tableRows = [];
      inTable = false;
    }
  };

  const parseInline = (text) => {
    let parts = [text];
    
    // Parse bold: **text**
    parts = parts.flatMap(part => {
      if (typeof part !== 'string') return part;
      const subparts = part.split('**');
      return subparts.map((sub, idx) => idx % 2 === 1 ? <strong key={idx}>{sub}</strong> : sub);
    });

    // Parse inline code: `code`
    parts = parts.flatMap(part => {
      if (typeof part !== 'string') return part;
      const subparts = part.split('`');
      return subparts.map((sub, idx) => idx % 2 === 1 ? <code key={idx} style={styles.inlineCode}>{sub}</code> : sub);
    });

    return parts;
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // 1. Code block handling
    if (trimmed.startsWith('```')) {
      if (inCodeBlock) {
        const blockContent = codeLines.join('\n');
        renderedElements.push(
          <pre key={`code-${i}`} style={styles.codeBlock}>
            {codeLang && <div style={styles.codeLang}>{codeLang}</div>}
            <code style={styles.codeText}>{blockContent}</code>
          </pre>
        );
        codeLines = [];
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
        codeLang = trimmed.substring(3).trim();
      }
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }

    // 2. Table handling
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      flushList(i);
      const cells = line.split('|').map(c => c.trim()).filter((c, idx, arr) => idx > 0 && idx < arr.length - 1);
      const isSeparator = cells.every(c => c.startsWith('-') || c === '');
      
      if (isSeparator) {
        continue;
      }

      if (!inTable) {
        inTable = true;
        tableHeaders = cells.map(c => parseInline(c));
      } else {
        tableRows.push(cells.map(c => parseInline(c)));
      }
      continue;
    } else if (inTable) {
      flushTable(i);
    }

    // 3. Lists handling
    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      inList = true;
      listItems.push(parseInline(trimmed.substring(2)));
      continue;
    } else if (inList) {
      flushList(i);
    }

    // 4. Headers and other block elements
    if (trimmed.startsWith('# ')) {
      renderedElements.push(<h2 key={i} style={styles.h1}>{parseInline(trimmed.substring(2))}</h2>);
    } else if (trimmed.startsWith('## ')) {
      renderedElements.push(<h3 key={i} style={styles.h2}>{parseInline(trimmed.substring(3))}</h3>);
    } else if (trimmed.startsWith('### ')) {
      renderedElements.push(<h4 key={i} style={styles.h3}>{parseInline(trimmed.substring(4))}</h4>);
    } else if (trimmed.startsWith('#### ')) {
      renderedElements.push(<h5 key={i} style={styles.h4}>{parseInline(trimmed.substring(5))}</h5>);
    } else if (trimmed.startsWith('> ')) {
      const quoteText = trimmed.substring(2);
      if (quoteText.startsWith('[!NOTE]')) {
        renderedElements.push(<div key={i} style={{ ...styles.alert, ...styles.alertNote }}>{parseInline(quoteText.substring(7).trim())}</div>);
      } else if (quoteText.startsWith('[!WARNING]')) {
        renderedElements.push(<div key={i} style={{ ...styles.alert, ...styles.alertWarning }}>{parseInline(quoteText.substring(10).trim())}</div>);
      } else if (quoteText.startsWith('[!IMPORTANT]')) {
        renderedElements.push(<div key={i} style={{ ...styles.alert, ...styles.alertImportant }}>{parseInline(quoteText.substring(12).trim())}</div>);
      } else {
        renderedElements.push(<blockquote key={i} style={styles.blockquote}>{parseInline(quoteText)}</blockquote>);
      }
    } else if (trimmed === '---' || trimmed === '***') {
      renderedElements.push(<hr key={i} style={styles.hr} />);
    } else if (trimmed !== '') {
      renderedElements.push(<p key={i} style={styles.p}>{parseInline(line)}</p>);
    }
  }

  flushList('eof');
  flushTable('eof');

  return <div style={styles.container}>{renderedElements}</div>;
}

const styles = {
  container: {
    fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
    color: 'var(--color-text)',
    lineHeight: 1.6,
    fontSize: '13px',
  },
  h1: { fontSize: '18px', fontWeight: 600, borderBottom: '1px solid var(--color-border-tertiary)', paddingBottom: '6px', marginTop: '20px', marginBottom: '10px', color: 'var(--color-text)' },
  h2: { fontSize: '15px', fontWeight: 600, marginTop: '16px', marginBottom: '8px', color: 'var(--color-text)' },
  h3: { fontSize: '13px', fontWeight: 600, marginTop: '14px', marginBottom: '6px', color: 'var(--color-text)' },
  h4: { fontSize: '12px', fontWeight: 600, marginTop: '12px', marginBottom: '6px', color: 'var(--color-text)' },
  p: { marginBottom: '10px', color: 'var(--color-text-secondary)' },
  ul: { paddingLeft: '20px', marginBottom: '10px' },
  li: { marginBottom: '3px', color: 'var(--color-text-secondary)' },
  hr: { border: 'none', borderBottom: '1px solid var(--color-border-tertiary)', margin: '16px 0' },
  blockquote: { borderLeft: '4px solid var(--color-border)', paddingLeft: '12px', margin: '0 0 10px 0', color: 'var(--color-text-tertiary)', fontStyle: 'italic' },
  alert: { padding: '8px 12px', borderRadius: 'var(--radius-md)', marginBottom: '10px', fontSize: '11px', fontWeight: 500 },
  alertNote: { background: 'var(--color-accent-muted)', borderLeft: '4px solid var(--color-accent)', color: 'var(--color-accent)' },
  alertWarning: { background: 'rgba(230, 126, 34, 0.1)', borderLeft: '4px solid #e67e22', color: '#e67e22' },
  alertImportant: { background: 'rgba(231, 76, 60, 0.1)', borderLeft: '4px solid var(--color-danger)', color: 'var(--color-danger)' },
  inlineCode: { background: 'var(--color-background-tertiary)', padding: '2px 4px', borderRadius: '3px', fontFamily: 'monospace', fontSize: '11px', color: 'var(--color-danger)' },
  codeBlock: { background: 'var(--color-background-tertiary)', borderRadius: 'var(--radius-md)', padding: '10px', overflowX: 'auto', marginBottom: '12px', border: '1px solid var(--color-border)', position: 'relative' },
  codeLang: { position: 'absolute', top: '4px', right: '8px', fontSize: '9px', textTransform: 'uppercase', color: 'var(--color-text-tertiary)', fontWeight: 600 },
  codeText: { fontFamily: 'Consolas, Monaco, monospace', fontSize: '11px', color: 'var(--color-text-secondary)' },
  tableWrapper: { overflowX: 'auto', marginBottom: '12px', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border)' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: '11px' },
  th: { background: 'var(--color-background-tertiary)', color: 'var(--color-text)', fontWeight: 600, padding: '6px 10px', textAlign: 'left', borderBottom: '1px solid var(--color-border)' },
  td: { padding: '6px 10px', borderBottom: '0.5px solid var(--color-border-tertiary)', color: 'var(--color-text-secondary)' },
  trEven: { background: 'transparent' },
  trOdd: { background: 'rgba(255,255,255,0.01)' }
};
