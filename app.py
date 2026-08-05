import os
import sys
import uuid
import tempfile
import atexit
import shutil
import base64
import webbrowser
from threading import Timer
from flask import Flask, request, jsonify, send_file, render_template

import fitz  # PyMuPDF

# Obter o caminho base, compatível com PyInstaller
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'), static_folder=os.path.join(BASE_DIR, 'static'))

# Diretório temporário para armazenar arquivos
TEMP_DIR = tempfile.mkdtemp()

# Dicionário para rastrear os arquivos enviados e seus nomes originais
uploaded_files = {}

def cleanup_temp_dir():
    """Remove o diretório temporário ao encerrar a aplicação."""
    try:
        shutil.rmtree(TEMP_DIR)
    except Exception as e:
        print(f"Erro ao limpar diretório temporário: {e}")

atexit.register(cleanup_temp_dir)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload_files():
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
        
        try:
            # Abrir o PDF com PyMuPDF
            doc = fitz.open(file_path)
            pages = len(doc)
            
            # Gerar miniatura da primeira página
            page = doc[0]
            # renderizar com aprox 200px de largura
            zoom = 200 / page.rect.width
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            # Converter para base64
            img_data = pix.tobytes("png")
            b64_img = base64.b64encode(img_data).decode('utf-8')
            thumbnail = f"data:image/png;base64,{b64_img}"
            
            doc.close()
            
            uploaded_files[file_id] = {
                "name": file.filename,
                "path": file_path
            }
            
            results.append({
                "id": file_id,
                "name": file.filename,
                "pages": pages,
                "thumbnail": thumbnail
            })
            
        except Exception as e:
            # Se falhar ao processar, remove o arquivo
            if os.path.exists(file_path):
                os.remove(file_path)
            print(f"Erro ao processar PDF {file.filename}: {e}")
            
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
    
    if position == 'top-left':
        return fitz.Rect(left_x1, top_y1, left_x2, top_y2), fitz.TEXT_ALIGN_LEFT
    elif position == 'top-center':
        return fitz.Rect(center_x1, top_y1, center_x2, top_y2), fitz.TEXT_ALIGN_CENTER
    elif position == 'top-right':
        return fitz.Rect(right_x1, top_y1, right_x2, top_y2), fitz.TEXT_ALIGN_RIGHT
    elif position == 'middle-left':
        return fitz.Rect(left_x1, middle_y1, left_x2, middle_y2), fitz.TEXT_ALIGN_LEFT
    elif position == 'middle-center':
        return fitz.Rect(center_x1, middle_y1, center_x2, middle_y2), fitz.TEXT_ALIGN_CENTER
    elif position == 'middle-right':
        return fitz.Rect(right_x1, middle_y1, right_x2, middle_y2), fitz.TEXT_ALIGN_RIGHT
    elif position == 'bottom-left':
        return fitz.Rect(left_x1, bottom_y1, left_x2, bottom_y2), fitz.TEXT_ALIGN_LEFT
    elif position == 'bottom-center':
        return fitz.Rect(center_x1, bottom_y1, center_x2, bottom_y2), fitz.TEXT_ALIGN_CENTER
    elif position == 'bottom-right':
        return fitz.Rect(right_x1, bottom_y1, right_x2, bottom_y2), fitz.TEXT_ALIGN_RIGHT
    else:
        # Padrão
        return fitz.Rect(center_x1, bottom_y1, center_x2, bottom_y2), fitz.TEXT_ALIGN_CENTER

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
        
        # 1 e 2: Criar PDF vazio e inserir cada PDF na ordem
        for path in paths_to_merge:
            doc = fitz.open(path)
            merged_doc.insert_pdf(doc)
            doc.close()
            
        total_pages = len(merged_doc)
        
        # 3: Aplicar numeração se habilitado
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
                text = ""
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
                if facing_pages and (i % 2 == 1): # i é 0-based, então página par visual (2, 4...) tem índice ímpar (1, 3...)
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
        
        # 5: Salvar temporariamente e enviar
        out_id = str(uuid.uuid4())
        out_path = os.path.join(TEMP_DIR, f"merged_{out_id}.pdf")
        merged_doc.save(out_path)
        merged_doc.close()
        
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
