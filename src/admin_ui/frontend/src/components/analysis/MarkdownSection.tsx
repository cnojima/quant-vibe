import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Card } from '../common/Card';

interface MarkdownSectionProps {
  title: string;
  content: string;
}

export const MarkdownSection: React.FC<MarkdownSectionProps> = ({
  title,
  content,
}) => {
  return (
    <Card>
      <h3 className="text-lg font-semibold mb-4">{title}</h3>
      <div
        className="prose prose-sm max-w-none
          prose-headings:font-semibold
          prose-h1:text-2xl prose-h1:mt-4 prose-h1:mb-2
          prose-h2:text-xl prose-h2:mt-3 prose-h2:mb-2
          prose-h3:text-lg prose-h3:mt-2 prose-h3:mb-1
          prose-p:my-2 prose-p:leading-relaxed
          prose-ul:my-2 prose-ul:pl-6
          prose-ol:my-2 prose-ol:pl-6
          prose-li:my-1
          prose-code:bg-gray-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:font-mono
          prose-pre:bg-gray-100 prose-pre:p-4 prose-pre:rounded prose-pre:overflow-auto
          prose-pre:my-3
          prose-strong:font-semibold
          prose-em:italic
          prose-blockquote:border-l-4 prose-blockquote:border-blue-500 prose-blockquote:pl-4 prose-blockquote:my-3 prose-blockquote:text-gray-700
          prose-table:border-collapse prose-table:w-full prose-table:my-3
          prose-th:border-b-2 prose-th:border-gray-300 prose-th:p-2 prose-th:text-left prose-th:font-semibold
          prose-td:border-b prose-td:border-gray-200 prose-td:p-2
        "
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
    </Card>
  );
};
