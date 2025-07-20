# dd_by_ifc/models.py

from django.db import models
import json

class ProjectDD(models.Model):
    project_name = models.CharField("프로젝트명", max_length=50)
    ifc_file = models.FileField("IFC 파일", upload_to='ifc_files/')

    def __str__(self):
        return self.project_name

class Project(models.Model):
    name = models.CharField(max_length=100)
    use = models.CharField(max_length=100)
    ifc_file = models.FileField(upload_to='ifc_files/')
    converted_obj = models.FileField(upload_to='converted_objs/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # IFC 처리 상태
    is_processed = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class ObjectIdMap(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    converted_id = models.CharField(max_length=100)
    global_id = models.CharField(max_length=100)

class CostCode(models.Model):
    """공사코드 정보"""
    code = models.CharField(max_length=50, unique=True, verbose_name="코드")
    category = models.CharField(max_length=100, verbose_name="공종")
    name = models.CharField(max_length=200, verbose_name="명칭")
    specification = models.CharField(max_length=200, verbose_name="규격")
    unit = models.CharField(max_length=50, verbose_name="단위")
    formula = models.TextField(verbose_name="산식")
    material_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="재료비단가")
    labor_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="노무비단가")
    expense_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="경비단가")
    total_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="합계단가")
    
    class Meta:
        ordering = ['code']
    
    def __str__(self):
        return f"{self.code} - {self.name}"

class IFCObject(models.Model):
    """IFC 객체 정보"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    global_id = models.CharField(max_length=100)
    name = models.CharField(max_length=200, blank=True)
    ifc_class = models.CharField(max_length=100)
    spatial_container = models.CharField(max_length=500, blank=True)
    
    # 수량 정보는 JSON 필드로 저장
    quantities = models.JSONField(default=dict)
    properties = models.JSONField(default=dict)
    
    # 공사코드 (+ 구분자로 여러개)
    cost_items = models.TextField(blank=True, verbose_name="CostItems")
    
    # 계산된 총금액
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    class Meta:
        unique_together = ['project', 'global_id']
    
    def __str__(self):
        return f"{self.ifc_class} - {self.name}"
    
    def get_cost_codes(self):
        """연결된 공사코드 리스트 반환 (+ 구분자)"""
        if not self.cost_items:
            return []
        return [code.strip() for code in self.cost_items.split("+") if code.strip()]
    
    def add_cost_code(self, code):
        """공사코드 추가 (+ 구분자)"""
        existing_codes = set(self.get_cost_codes())
        existing_codes.add(code)
        self.cost_items = "+".join(sorted(existing_codes))
        self.save()
    
    def remove_cost_code(self, code):
        """공사코드 제거"""
        existing_codes = set(self.get_cost_codes())
        existing_codes.discard(code)
        self.cost_items = "+".join(sorted(existing_codes))
        self.save()
    
    def calculate_total_amount(self):
        """총금액 계산"""
        total = 0
        codes = self.get_cost_codes()
        
        for code in codes:
            try:
                cost_code = CostCode.objects.get(code=code)
                
                # 수량 계산을 위한 컨텍스트 준비
                context = {**self.quantities, **self.properties}
                context.update({
                    'GlobalId': self.global_id,
                    'Name': self.name,
                    'IfcClass': self.ifc_class,
                    'SpatialContainer': self.spatial_container,
                })
                
                # 산식 계산
                try:
                    quantity = eval(cost_code.formula, {"__builtins__": None}, context)
                except:
                    quantity = 0
                
                total += quantity * float(cost_code.total_cost)
            except CostCode.DoesNotExist:
                continue
            except Exception as e:
                print(f"계산 오류: {e}")
                continue
        
        self.total_amount = total
        self.save()
        return total