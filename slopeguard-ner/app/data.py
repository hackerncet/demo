"""Illustrative pilot locations; road geometry and exposure are demonstration data."""
from .risk import predict

SEEDS = [
 ('SG-01','Lachung corridor','Sikkim','Mangan',27.61,88.64,'NH-310A',230,610,92,48,9,42,4200,'Restricted'),
 ('SG-02','Dikchu hillside','Sikkim','Gangtok',27.40,88.53,'NH-10',166,470,84,43,7,34,2800,'Caution'),
 ('SG-03','Sohra ridge','Meghalaya','East Khasi Hills',25.27,91.73,'SH-5',198,540,88,39,6,28,3600,'Caution'),
 ('SG-04','Aizawl eastern slope','Mizoram','Aizawl',23.73,92.74,'NH-54',145,390,81,41,6,35,6100,'Caution'),
 ('SG-05','Itanagar foothills','Arunachal Pradesh','Papum Pare',27.09,93.61,'NH-415',124,340,76,38,5,20,3100,'Open'),
 ('SG-06','Kohima bypass','Nagaland','Kohima',25.67,94.11,'NH-29',118,318,74,35,4,24,2700,'Open'),
 ('SG-07','Noney valley road','Manipur','Noney',24.85,93.67,'NH-37',156,410,85,46,8,45,1900,'Restricted'),
 ('SG-08','Haflong approach','Assam','Dima Hasao',25.17,93.02,'NH-27',110,320,72,37,5,23,2400,'Caution'),
 ('SG-09','Unakoti approach','Tripura','Unakoti',24.32,92.06,'NH-8',58,156,57,24,2,12,1800,'Open'),
 ('SG-10','Tawang pass','Arunachal Pradesh','Tawang',27.59,91.87,'NH-13',82,240,64,51,6,17,1200,'Open'),
 ('SG-11','Shillong plateau','Meghalaya','East Khasi Hills',25.57,91.88,'NH-6',76,220,61,28,3,15,4700,'Open'),
 ('SG-12','Guwahati foothills','Assam','Kamrup Metro',26.14,91.74,'NH-27',24,85,43,18,1,8,8200,'Open'),
 ('SG-13','Gangtok urban ridge','Sikkim','Gangtok',27.33,88.61,'NH-10',90,265,69,37,5,21,5400,'Caution'),
 ('SG-14','Imphal eastern edge','Manipur','Imphal East',24.81,94.00,'NH-202',32,105,48,19,1,9,3500,'Open'),
 ('SG-15','Agartala outer hills','Tripura','West Tripura',23.83,91.29,'NH-8',18,64,39,14,0,5,2300,'Open'),
 ('SG-16','Dimapur approach','Nagaland','Chumoukedima',25.79,93.83,'NH-29',46,144,52,22,2,11,3200,'Open'),
]

def locations():
    out=[]
    for row in SEEDS:
        ident,name,state,district,lat,lon,road,r24,r72,soil,slope,past,veg,pop,status=row
        features=dict(zip(['rainfall_24h','rainfall_72h','soil_moisture','slope','past_incidents','vegetation_loss'],[r24,r72,soil,slope,past,veg]))
        out.append(dict(id=ident,name=name,state=state,district=district,lat=lat,lon=lon,road=road,
                        population=pop,road_status=status,features=features,risk=predict(features),
                        source='Illustrative pilot scenario',infrastructure=['Primary health centre','Community shelter'],
                        geometry=[[lat-.025,lon-.04],[lat-.008,lon-.014],[lat,lon],[lat+.023,lon+.035]],
                        updated_at='Scenario snapshot',satellite_status='Illustrative vegetation-loss feature'))
    return out
