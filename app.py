import os
import sys
import uuid
import tempfile
import atexit
import shutil
import base64
import webbrowser
import gc
from io import BytesIO
from threading import Timer
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, send_file, render_template

import fitz  # PyMuPDF

# Obter o caminho base, compatível com PyInstaller
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'), static_folder=os.path.join(BASE_DIR, 'static'))

# Aumentar limite de upload (500MB)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

# Diretório temporário para armazenar arquivos
TEMP_DIR = tempfile.mkdtemp()

# Dicionário para rastrear os arquivos enviados e seus nomes originais
uploaded_files = {}

# Pool de threads para processamento paralelo
executor = ThreadPoolExecutor(max_workers=4)

# Configurações de thumbnail otimizadas
THUMB_WIDTH = 150  # px - menor para transferência mais rápida
THUMB_QUALITY = 60  # Qualidade JPEG (0-100)


def cleanup_temp_dir():
    """Remove o diretório temporário ao encerrar a aplicação."""
    try:
        shutil.rmtree(TEMP_DIR)
    except Exception as e:
        print(f"Erro ao limpar diretório temporário: {e}")

atexit.register(cleanup_temp_dir)


def process_single_pdf(file_path, original_name):
    """Processa um único PDF: conta páginas e gera thumbnail JPEG otimizada."""
    try:
        doc = fitz.open(file_path)
        pages = len(doc)

        # Gerar miniatura da primeira página com resolução reduzida
        page = doc[0]
        zoom = THUMB_WIDTH / page.rect.width
        mat = fitz.Matrix(zoom, zoom)

        # Usar alpha=False para evitar canal de transparência (mais leve)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        # Converter para JPEG (muito menor que PNG)
        # PyMuPDF suporta saída direta em JPEG
        img_data = pix.tobytes("jpeg")
        b64_img = base64.b64encode(img_data).decode('utf-8')
        thumbnail = f"data:image/jpeg;base64,{b64_img}"

        doc.close()

        return {
            "name": original_name,
            "pages": pages,
            "thumbnail": thumbnail
        }

    except Exception as e:
        print(f"Erro ao processar PDF {original_name}: {e}")
        return {
            "name": original_name,
            "pages": 0,
            "thumbnail": None,
            "error": str(e)
        }


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/upload-single', methods=['POST'])
def upload_single_file():
    """Upload otimizado: processa um arquivo por vez para feedback imediato."""
    if 'file' not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nome de arquivo vazio"}), 400

    file_id = str(uuid.uuid4())
    file_path = os.path.join(TEMP_DIR, file_id + ".pdf")
    file.save(file_path)

    result = process_single_pdf(file_path, file.filename)

    if result.get("error"):
        if os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({"error": f"Falha ao processar: {result['error']}"}), 400

    uploaded_files[file_id] = {
        "name": file.filename,
        "path": file_path
    }

    result["id"] = file_id
    return jsonify(result)


@app.route('/api/upload', methods=['POST'])
def upload_files():
    """Upload em lote (compatibilidade). Para melhor performance, usar /api/upload-single."""
    if 'files' not in request.files and 'file' not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    files = request.files.getlist('files')
    if not files:
        files = request.files.getlist('file')

    if not files:
        return jsonify({"error": "Lista de arquivos vazia"}), 400

    results = []

    for file in files:
        if file.filename == '':
            continue

        file_id = str(uuid.uuid4())
        file_path = os.path.join(TEMP_DIR, file_id + ".pdf")
        file.save(file_path)

        result = process_single_pdf(file_path, file.filename)

        if result.get("error"):
            if os.path.exists(file_path):
                os.remove(file_path)
            continue

        uploaded_files[file_id] = {
            "name": file.filename,
            "path": file_path
        }

        result["id"] = file_id
        results.append(result)

    return jsonify(results)


def get_position_rect(page_rect, position, margin, font_size):
    """Calcula o retângulo de inserção de texto com base na posição."""
    width = page_rect.width
    height = page_rect.height

    # Altura do bloco de texto (aproximada)
    h_box = font_size + 10

    # Coordenadas X
    left_x1 = margin
    left_x2 = width / 3

    center_x1 = width / 3
    center_x2 = 2 * width / 3

    right_x1 = 2 * width / 3
    right_x2 = width - margin

    # Coordenadas Y
    top_y1 = margin
    top_y2 = margin + h_box

    middle_y1 = (height / 2) - (h_box / 2)
    middle_y2 = (height / 2) + (h_box / 2)

    bottom_y1 = height - margin - h_box
    bottom_y2 = height - margin

    positions = {
        'top-left':      (fitz.Rect(left_x1, top_y1, left_x2, top_y2), fitz.TEXT_ALIGN_LEFT),
        'top-center':    (fitz.Rect(center_x1, top_y1, center_x2, top_y2), fitz.TEXT_ALIGN_CENTER),
        'top-right':     (fitz.Rect(right_x1, top_y1, right_x2, top_y2), fitz.TEXT_ALIGN_RIGHT),
        'middle-left':   (fitz.Rect(left_x1, middle_y1, left_x2, middle_y2), fitz.TEXT_ALIGN_LEFT),
        'middle-center': (fitz.Rect(center_x1, middle_y1, center_x2, middle_y2), fitz.TEXT_ALIGN_CENTER),
        'middle-right':  (fitz.Rect(right_x1, middle_y1, right_x2, middle_y2), fitz.TEXT_ALIGN_RIGHT),
        'bottom-left':   (fitz.Rect(left_x1, bottom_y1, left_x2, bottom_y2), fitz.TEXT_ALIGN_LEFT),
        'bottom-center': (fitz.Rect(center_x1, bottom_y1, center_x2, bottom_y2), fitz.TEXT_ALIGN_CENTER),
        'bottom-right':  (fitz.Rect(right_x1, bottom_y1, right_x2, bottom_y2), fitz.TEXT_ALIGN_RIGHT),
    }

    return positions.get(position, positions['bottom-center'])


@app.route('/api/merge', methods=['POST'])
def merge_files():
    data = request.json
    if not data or 'files' not in data:
        return jsonify({"error": "Lista de arquivos não fornecida"}), 400

    file_ids = data['files']
    if not file_ids:
        return jsonify({"error": "Lista de arquivos vazia"}), 400

    # Verificar se todos os arquivos existem
    paths_to_merge = []
    for fid in file_ids:
        if fid not in uploaded_files:
            return jsonify({"error": f"Arquivo não encontrado: {fid}"}), 404
        path = uploaded_files[fid]['path']
        if not os.path.exists(path):
            return jsonify({"error": f"Arquivo não existe no disco: {fid}"}), 404
        paths_to_merge.append(path)

    numbering = data.get('numbering', {})
    num_enabled = numbering.get('enabled', False)

    try:
        merged_doc = fitz.open()

        # Inserir cada PDF na ordem, fechando imediatamente para liberar memória
        for path in paths_to_merge:
            doc = fitz.open(path)
            merged_doc.insert_pdf(doc)
            doc.close()
            del doc

        # Forçar coleta de lixo após inserir PDFs pesados
        gc.collect()

        total_pages = len(merged_doc)

        # Aplicar numeração se habilitado
        if num_enabled and total_pages > 0:
            position = numbering.get('position', 'bottom-center')
            num_format = numbering.get('format', 'page_of_total')
            start_page = int(numbering.get('start_page', 1))
            font_size = float(numbering.get('font_size', 12))
            color = numbering.get('color', [0, 0, 0])
            # Converter cor de [0-255] para [0-1]
            if any(c > 1 for c in color):
                color = [c / 255.0 for c in color]
            margin = float(numbering.get('margin', 30))
            facing_pages = numbering.get('facing_pages', False)

            for i in range(total_pages):
                page = merged_doc[i]
                current_num = start_page + i

                # Formatar o texto
                if num_format == 'number':
                    text = f"{current_num}"
                elif num_format == 'page_n':
                    text = f"Página {current_num}"
                elif num_format == 'n_of_total':
                    text = f"{current_num} de {total_pages}"
                elif num_format == 'page_n_of_total':
                    text = f"Página {current_num} de {total_pages}"
                else:
                    text = f"{current_num}"

                # Ajustar posição para páginas espelhadas (facing pages)
                current_position = position
                if facing_pages and (i % 2 == 1):
                    if 'left' in current_position:
                        current_position = current_position.replace('left', 'right')
                    elif 'right' in current_position:
                        current_position = current_position.replace('right', 'left')

                rect, align = get_position_rect(page.rect, current_position, margin, font_size)

                page.insert_textbox(
                    rect,
                    text,
                    fontsize=font_size,
                    fontname="helv",
                    color=color,
                    align=align
                )

        # Salvar com garbage collection e limpeza do PDF
        out_id = str(uuid.uuid4())
        out_path = os.path.join(TEMP_DIR, f"merged_{out_id}.pdf")
        merged_doc.save(out_path, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True)
        merged_doc.close()
        del merged_doc
        gc.collect()

        return send_file(
            out_path,
            as_attachment=True,
            download_name='FAPEMIG_PDFs_compilado.pdf',
            mimetype='application/pdf'
        )

    except Exception as e:
        return jsonify({"error": f"Falha ao mesclar PDFs: {str(e)}"}), 500


@app.route('/api/files/<file_id>', methods=['DELETE'])
def delete_file(file_id):
    if file_id in uploaded_files:
        path = uploaded_files[file_id]['path']
        try:
            if os.path.exists(path):
                os.remove(path)
            del uploaded_files[file_id]
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "Arquivo não encontrado"}), 404

@app.route('/api/files', methods=['DELETE'])
def delete_all_files():
    errors = []
    for file_id, info in list(uploaded_files.items()):
        path = info['path']
        try:
            if os.path.exists(path):
                os.remove(path)
            del uploaded_files[file_id]
        except Exception as e:
            errors.append(f"Erro ao remover {file_id}: {str(e)}")

    if errors:
        return jsonify({"error": "Alguns arquivos não puderam ser removidos", "details": errors}), 500

    return jsonify({"success": True})

def open_browser():
    """Abre o navegador em modo app (sem barra de URL), similar ao WhatsApp Web desktop."""
    import subprocess
    url = 'http://localhost:5000'

    # Caminhos comuns do Chrome e Edge no Windows
    browsers = [
        # Google Chrome
        os.path.join(os.environ.get('PROGRAMFILES', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
        os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
        # Microsoft Edge
        os.path.join(os.environ.get('PROGRAMFILES', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    ]

    for browser_path in browsers:
        if os.path.exists(browser_path):
            try:
                subprocess.Popen([browser_path, f'--app={url}', '--new-window'])
                return
            except Exception:
                continue

    # Fallback: abrir no navegador padrão (com barra de URL)
    webbrowser.open(url)

if __name__ == '__main__':
    Timer(1.5, open_browser).start()
    app.run(host='localhost', port=5000)
