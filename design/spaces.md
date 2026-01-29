Spaces
- Repo
[e.g. https://huggingface.co/spaces/vivienfanghua/wan2.2_enhanced_amd]
- Src Meta
{
    src: ModelScope
    outer_email:xxx
    inner_uid: xxx
    xxxxxx
}
- Start Command
[e.g. python3 main.py]
- Resources
[Free CPU xx Cores yy Memorys, zz Gi SSD] 
[AMD MI300X * 1, xx Cores, yy Memorys, zz Gi SSD]
[AMD MI300X * 2, xx Cores, yy Memorys, zz Gi SSD]
[AMD MI300X * 4, xx Cores, yy Memorys, zz Gi SSD]
[AMD MI300X * 8, xx Cores, yy Memorys, zz Gi SSD]
[AMD MI355X * 1, xx Cores, yy Memorys, zz Gi SSD]
[AMD MI355X * 2, xx Cores, yy Memorys, zz Gi SSD]
[AMD MI355X * 4, xx Cores, yy Memorys, zz Gi SSD]
[AMD MI355X * 8, xx Cores, yy Memorys, zz Gi SSD]
[AMD R7900 * 1, xx Cores, yy Memorys, zz Gi SSD]
[AMD R7900 * 2, xx Cores, yy Memorys, zz Gi SSD]
[AMD R7900 * 4, xx Cores, yy Memorys, zz Gi SSD]
[AMD R7900 * 8, xx Cores, yy Memorys, zz Gi SSD]

Optional:
- Env
-- Docker Image
default: [rocm/vllm-dev:nightly_main_20260125]
[rocm/pytorch:rocm7.2_ubuntu24.04_py3.12_pytorch_release_2.7.1]
-- Environments
[pre installed conda python3.10(we provide remote tar packages, will be downloaded while starting instance)]
[pre installed conda python3.11]
[pre installed conda python3.12]
-- Custom Port
e.g. 8006((Binded in service to target Port))
-- Environment Variables
ENV_A=b



