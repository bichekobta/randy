# Importaciones necesarias
from flask import Flask, render_template, request, send_file, jsonify
from PIL import Image
import numpy as np
import cv2
import io
import os
import base64
from werkzeug.utils import secure_filename
import logging

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__, 
           template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))

# Configuración de carga de archivos
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'tiff'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    try:
        return render_template('Randys2.html')
    except Exception as e:
        logger.error(f"Error rendering template: {str(e)}")
        return f"Error: {str(e)}", 500

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No se seleccionó ningún archivo'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No se seleccionó ningún archivo'}), 400
            
        if not allowed_file(file.filename):
            return jsonify({'error': f'Tipo de archivo no permitido. Use: {", ".join(ALLOWED_EXTENSIONS)}'}), 400

        try:
            # Procesar imagen
            img = Image.open(file)
            
            # Convertir a RGB si es necesario
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Redimensionar si la imagen es muy grande
            max_size = 1200
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = tuple(int(dim * ratio) for dim in img.size)
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Convertir imagen a base64 para mostrar en el template
            img_io = io.BytesIO()
            img.save(img_io, 'JPEG', quality=85)
            img_io.seek(0)
            img_base64 = base64.b64encode(img_io.getvalue()).decode()
            
            return jsonify({
                'original': f'data:image/jpeg;base64,{img_base64}',
                'preview': f'data:image/jpeg;base64,{img_base64}'  # Por ahora es la misma
            })
            
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            return jsonify({'error': f'Error al procesar la imagen: {str(e)}'}), 400
            
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({'error': f'Error inesperado: {str(e)}'}), 500

@app.route('/preview', methods=['POST'])
def preview_lut():
    try:
        # Obtener parámetros
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No se recibieron datos'}), 400
            
        image_data = data.get('image', '').split(',')[1]  # Remover el prefijo data:image/jpeg;base64,
        tone = data.get('tone', 'neutral')
        contrast = float(data.get('contrast', 50)) / 100.0
        saturation = float(data.get('saturation', 50)) / 100.0
        style = data.get('style', 'classic')
        
        # Decodificar imagen
        img_data = base64.b64decode(image_data)
        img = Image.open(io.BytesIO(img_data))
        
        # Convertir a numpy array
        img_array = np.array(img)
        
        # Aplicar ajustes
        img_array = apply_adjustments(img_array, tone, contrast, saturation, style)
        
        # Convertir de vuelta a imagen
        result_img = Image.fromarray(img_array)
        
        # Convertir a base64
        img_io = io.BytesIO()
        result_img.save(img_io, 'JPEG', quality=85)
        img_io.seek(0)
        preview_base64 = base64.b64encode(img_io.getvalue()).decode()
        
        return jsonify({
            'preview': f'data:image/jpeg;base64,{preview_base64}'
        })
        
    except Exception as e:
        logger.error(f"Error generating preview: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/generate-lut', methods=['POST'])
def generate_lut():
    try:
        # Obtener parámetros
        data = request.get_json()
        if not data:
            logger.error("No se recibieron datos")
            return jsonify({'error': 'No se recibieron datos'}), 400
            
        # Validar y convertir parámetros
        try:
            tone = str(data.get('tone', 'neutral'))
            contrast = float(data.get('contrast', 50)) / 100.0
            saturation = float(data.get('saturation', 50)) / 100.0
            style = str(data.get('style', 'classic'))
            
            logger.debug(f"Parámetros recibidos: tone={tone}, contrast={contrast}, saturation={saturation}, style={style}")
            
            # Validar rangos
            if not (0 <= contrast <= 2) or not (0 <= saturation <= 2):
                raise ValueError("Valores de contraste o saturación fuera de rango")
                
            if tone not in ['neutral', 'warm', 'cold', 'green']:
                raise ValueError("Tono no válido")
                
            if style not in ['classic', 'kodak', 'scifi', 'tarantino']:
                raise ValueError("Estilo no válido")
                
        except (ValueError, TypeError) as e:
            logger.error(f"Error en los parámetros: {str(e)}")
            return jsonify({'error': f'Parámetros inválidos: {str(e)}'}), 400
            
        try:
            # Generar LUT
            lut_content = generate_cube_file(tone, contrast, saturation, style)
            
            # Crear archivo temporal
            temp_file = io.BytesIO()
            temp_file.write(lut_content.encode('utf-8'))
            temp_file.seek(0)
            
            return send_file(
                temp_file,
                mimetype='text/plain',
                as_attachment=True,
                download_name='color_correction.cube'
            )
            
        except Exception as e:
            logger.error(f"Error generando LUT: {str(e)}")
            return jsonify({'error': f'Error al generar el LUT: {str(e)}'}), 500
            
    except Exception as e:
        logger.error(f"Error inesperado: {str(e)}")
        return jsonify({'error': f'Error inesperado: {str(e)}'}), 500

def apply_adjustments(img_array, tone, contrast, saturation, style):
    try:
        logger.debug(f"Input image shape: {img_array.shape}, dtype: {img_array.dtype}")
        
        # Ensure we're working with a 3D array
        if len(img_array.shape) == 2:
            img_array = img_array.reshape(-1, 1, 3)
        
        # Convert to float32 for calculations
        img = img_array.astype(np.float32) / 255.0
        
        # Apply tone adjustments
        if tone == 'warm':
            img[..., 2] *= 1.1  # More red
            img[..., 0] *= 0.9  # Less blue
        elif tone == 'cold':
            img[..., 2] *= 0.9  # Less red
            img[..., 0] *= 1.1  # More blue
        elif tone == 'green':
            img[..., 1] *= 1.1  # More green
            
        # Apply contrast
        mean = np.mean(img, axis=(0, 1), keepdims=True)
        img = (img - mean) * (1 + contrast) + mean
        
        # Convert to HSV for saturation adjustment
        img_reshaped = img.reshape(-1, 3)  # Reshape to 2D for cv2.cvtColor
        hsv = cv2.cvtColor(img_reshaped.reshape(-1, 1, 3), cv2.COLOR_RGB2HSV)
        hsv[..., 1] *= saturation
        img = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB).reshape(img.shape)
        
        # Apply style adjustments
        if style == 'classic':
            img = img * 0.9 + 0.1
        elif style == 'kodak':
            img[..., 2] *= 1.1  # More red
            img[..., 0] *= 0.9  # Less blue
        elif style == 'scifi':
            img[..., 0] *= 1.2  # More blue
            img = img * 1.1
        elif style == 'tarantino':
            img[..., 2] *= 1.2  # More red
            img = img * 1.2
        
        # Ensure values are in range [0,1]
        img = np.clip(img, 0, 1)
        
        # Convert back to uint8
        return (img * 255).astype(np.uint8)
        
    except Exception as e:
        logger.error(f"Error in apply_adjustments: {str(e)}")
        logger.error(f"Image shape: {img_array.shape}, dtype: {img_array.dtype}")
        raise

def generate_cube_file(tone, contrast, saturation, style):
    try:
        logger.debug(f"Generating LUT with parameters: tone={tone}, contrast={contrast}, saturation={saturation}, style={style}")
        size = 32
        header = f"""#Created with LUT Generator
#Copyright 2024
LUT_3D_SIZE {size}
DOMAIN_MIN 0 0 0
DOMAIN_MAX 1 1 1
"""
        content = [header]
        
        try:
            # Create base RGB grid
            indices = np.linspace(0, 1, size)
            x, y, z = np.meshgrid(indices, indices, indices, indexing='ij')
            grid = np.stack([x, y, z], axis=-1)
            
            # Reshape to 2D array of RGB values
            grid_2d = grid.reshape(-1, 3)
            
            # Convert to uint8 for OpenCV processing
            grid_uint8 = (grid_2d * 255).astype(np.uint8)
            
            logger.debug(f"Grid shape before processing: {grid_uint8.shape}")
            logger.debug(f"Grid data type: {grid_uint8.dtype}")
            
            # Process in smaller batches
            batch_size = 4096
            result = np.zeros_like(grid_2d, dtype=np.float32)
            
            for i in range(0, len(grid_uint8), batch_size):
                batch = grid_uint8[i:i + batch_size]
                # Ensure batch has correct shape for OpenCV
                if len(batch.shape) == 2:
                    batch = batch.reshape(-1, 1, 3)
                
                # Apply color adjustments
                processed = apply_adjustments(batch, tone, contrast, saturation, style)
                
                # Reshape back and store
                if len(processed.shape) == 3:
                    processed = processed.reshape(-1, 3)
                result[i:i + batch_size] = processed.astype(np.float32) / 255.0
            
            # Generate LUT content
            for rgb in result:
                content.append(f"{rgb[0]:.6f} {rgb[1]:.6f} {rgb[2]:.6f}")
            
            return '\n'.join(content)
            
        except np.MemoryError as me:
            logger.error("Memory error during LUT generation")
            raise Exception("Error de memoria al generar el LUT")
        except Exception as e:
            logger.error(f"Error processing LUT data: {str(e)}")
            raise
            
    except Exception as e:
        logger.error(f"Error in generate_cube_file: {str(e)}")
        raise

if __name__ == '__main__':
    # Asegurar que el directorio de uploads existe
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    
    # Obtener puerto del entorno (para servicios cloud) o usar 5000 por defecto
    port = int(os.environ.get('PORT', 5000))
    
    # Imprimir información de depuración
    logger.info(f"Template folder: {app.template_folder}")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"Upload folder: {UPLOAD_FOLDER}")
    logger.info(f"OpenCV version: {cv2.__version__}")
    
    # Ejecutar la aplicación
    app.run(host='0.0.0.0', port=port, debug=False)
