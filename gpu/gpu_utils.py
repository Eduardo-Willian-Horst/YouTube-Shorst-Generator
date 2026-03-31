import subprocess
import json


def verificar_gpu_disponivel():
    try:
        resultado = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total,memory.free,utilization.gpu,temperature.gpu', '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            check=True
        )
        
        linhas = resultado.stdout.strip().split('\n')
        gpus = []
        
        for idx, linha in enumerate(linhas):
            partes = [p.strip() for p in linha.split(',')]
            if len(partes) >= 5:
                gpus.append({
                    'id': idx,
                    'nome': partes[0],
                    'memoria_total_mb': int(partes[1]) if partes[1].isdigit() else 0,
                    'memoria_livre_mb': int(partes[2]) if partes[2].isdigit() else 0,
                    'utilizacao_percent': int(partes[3]) if partes[3].isdigit() else 0,
                    'temperatura_celsius': int(partes[4]) if partes[4].isdigit() else 0,
                })
        
        return {'disponivel': True, 'gpus': gpus}
    except FileNotFoundError:
        return {'disponivel': False, 'erro': 'nvidia-smi não encontrado. GPU NVIDIA pode não estar disponível.'}
    except subprocess.CalledProcessError as e:
        return {'disponivel': False, 'erro': f'Erro ao executar nvidia-smi: {str(e)}'}


def obter_info_gpu_detalhada():
    try:
        resultado = subprocess.run(
            ['nvidia-smi', '--query-gpu=index,name,driver_version,memory.total,memory.used,memory.free,utilization.gpu,utilization.memory,temperature.gpu,power.draw', '--format=json'],
            capture_output=True,
            text=True,
            check=True
        )
        
        dados = json.loads(resultado.stdout)
        return {'disponivel': True, 'dados': dados}
    except FileNotFoundError:
        return {'disponivel': False, 'erro': 'nvidia-smi não encontrado.'}
    except json.JSONDecodeError:
        return {'disponivel': False, 'erro': 'Erro ao decodificar resposta do nvidia-smi.'}
    except subprocess.CalledProcessError as e:
        return {'disponivel': False, 'erro': f'Erro ao executar nvidia-smi: {str(e)}'}


def verificar_cuda_disponivel():
    try:
        import torch
        cuda_disponivel = torch.cuda.is_available()
        
        if cuda_disponivel:
            return {
                'disponivel': True,
                'versao_cuda': torch.version.cuda,
                'num_gpus': torch.cuda.device_count(),
                'nome_gpu': torch.cuda.get_device_name(0) if torch.cuda.device_count() > 0 else None
            }
        else:
            return {'disponivel': False, 'erro': 'CUDA não está disponível no PyTorch.'}
    except ImportError:
        return {'disponivel': False, 'erro': 'PyTorch não está instalado.'}
