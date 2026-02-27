import React from 'react';

const DataTable = ({ columns, rows, page, pageSize, rowCount, onPageChange }) => {
  const totalPages = Math.max(1, Math.ceil((rowCount || 0) / pageSize));
  const canPrev = page > 1;
  const canNext = page < totalPages;

  return (
    <div className="table-shell">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length || 1} className="empty-row">
                Sin resultados
              </td>
            </tr>
          ) : (
            rows.map((row, idx) => (
              <tr key={`${row.id || idx}`}>
                {columns.map((column) => (
                  <td key={`${column}-${idx}`}>{row[column] ?? '-'}</td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>

      <div className="pagination">
        <button disabled={!canPrev} onClick={() => onPageChange(page - 1)}>
          «
        </button>
        <span>
          Página {page} / {totalPages} · {rowCount} registros
        </span>
        <button disabled={!canNext} onClick={() => onPageChange(page + 1)}>
          »
        </button>
      </div>
    </div>
  );
};

export default DataTable;
